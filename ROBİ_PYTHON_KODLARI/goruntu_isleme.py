# =============================================================================
# 👁️ OPENCV BİLGİSAYARLI GÖRÜSÜ VE DURUŞ (POSTÜR) ANALİZ MOTORU (goruntu_isleme.py)
# =============================================================================
# Bu modül, ESP32-CAM'den gelen ham grayscale (gri ton) piksel verilerini TCP soketinden
# yakalar, Haar Cascade algoritması ile yüz takibi yapar, kullanıcının ergonomik duruşunu
# (kamburluk) ve masadan uzaklaşma durumunu (kaytarma) gerçek zamanlı hesaplar.

import cv2
import threading
import time
import socket
import numpy as np
from PIL import Image
import customtkinter as ctk

class GoruntuIslemeMotoru:
    def __init__(self, kamera_id="http://<YOUR_ESP32_CAM_IP>:81/stream", robi_donanim=None, arayuz_referansi=None):
        self.kamera_id = kamera_id  
        self.donanim = robi_donanim
        self.arayuz = arayuz_referansi
        self.aktif = False
        self.thread = None
        
        # Analitik Filtre Sayaçları (Hatalı frame'leri süzmek için)
        self.kambur_sayac = 0
        self.referans_y = None  # Kalibrasyon anındaki ideal kafa yüksekliği
        self.yokluk_sayac = 0  
        
        # OpenCV'nin hafif ve hızlı yüz bulma modelini yüklüyoruz.
        self.yuz_bulucu = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def baslat(self):
        # GUI thread'ini dondurmamak için görüntü yakalama döngüsünü arka planda (Daemon) başlatıyoruz.
        self.aktif = True
        self.thread = threading.Thread(target=self._ana_kamera_yoneticisi, daemon=True)
        self.thread.start()
        print(f"[KAMERA] Görüntü işleme ve analiz motoru başlatıldı.")

    def _ana_kamera_yoneticisi(self):
        # Varsayılan network konfigürasyonu yer tutucu IP adresine çekilmiştir.
        ip = "127.0.0.1"
        port = 81

        # Gelen kamera URI'sinden IP ve Port ayrıştırma işlemi.
        if "http://" in str(self.kamera_id) and "<YOUR_ESP32_CAM_IP>" not in str(self.kamera_id):
            try:
                temiz_url = self.kamera_id.replace("http://", "").split("/")[0]
                if ":" in temiz_url:
                    ip, port_str = temiz_url.split(":")
                    port = int(port_str)
                else:
                    ip = temiz_url
            except Exception as e:
                print(f"[UYARI] URL ayrıştırılamadı, varsayılan değerler kullanılacak: {e}")

        # --- 🛡️ 3 HAKLI BAĞLANTI GÜVENLİK MOTORU ---
        # Donanım geç açılabilir veya ağda kopma yaşanabilir. Sistem 3 kez dener,
        # eğer kablosuz kameraya bağlanamazsa çökmez, yerel web kamerasına (fallback) düşer.
        maks_deneme = 3
        baglandi = False

        for deneme in range(1, maks_deneme + 1):
            if ip == "127.0.0.1":
                break
                
            print(f"[KAMERA] ESP32-CAM Soketine Bağlanılıyor... Deneme {deneme}/{maks_deneme}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0) # 5 saniye zaman aşımı koruması
            
            try:
                sock.connect((ip, port))
                sock.settimeout(None) # Akış başladığında zaman aşımını kaldırıyoruz
                print(f"[KAMERA] ESP32-CAM Ham Grayscale Soketine Bağlanıldı -> {ip}:{port}")
                baglandi = True
                self._esp32_cam_soket_dongusu(sock)
                break
            except Exception as e:
                print(f"[UYARI] Deneme {deneme} başarısız oldu. Hata: {e}")
                sock.close()
                if deneme < maks_deneme:
                    time.sleep(2)

        if not baglandi:
            # Kablosuz donanıma erişilemediği senaryoda yerel web kamerası devreye alınır.
            print(f"[HATA] ESP32-CAM soketine erişilemedi! Yerel PC web kamerasına dönülüyor...")
            self._yerel_kamera_dongusu()

    def _esp32_cam_soket_dongusu(self, sock):
        """ ESP32-CAM'den paket sarmalı olmadan gelen ham piksel stream'ini işleyen döngü. """
        fw, fh = 320, 240 # ESP32 tarafında set edilen çözünürlük [cite: 612]
        frame_size = fw * fh # Toplam frame boyutu (Grayscale olduğu için 1 piksel = 1 bayt)
        buffer = b""

        while self.aktif:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    print("[KAMERA] ESP32-CAM veri akışını kesti.")
                    break
                buffer += chunk

                # Buffer içinde en az 1 tam kare veri biriktiyse işlemeye başla
                while len(buffer) >= frame_size:
                    frame_data = buffer[:frame_size]
                    buffer = buffer[frame_size:]

                    # Ham bayt dizisini 2 boyutlu OpenCV matrisine döküyoruz
                    frame = np.frombuffer(frame_data, dtype=np.uint8).reshape((fh, fw))
                    frame = cv2.flip(frame, 1) # Ayna efekti düzeltmesi

                    # Görüntüyü GUI ekranına bas ve biyometrik analize gönder
                    self._ekrana_goruntu_gonder(frame)
                    self._yuz_ve_postur_analizi(frame, fw, fh)

            except Exception as e:
                print(f"[HATA] ESP32-CAM Soket akışında hata: {e}")
                break
        
        sock.close()

    def _yerel_kamera_dongusu(self):
        """ PC Yerel Web Kamerası (Webcam) Okuma Döngüsü """
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[HATA] Yerel web kamerasına da erişilemedi! Görüntü işleme tamamen pasif.")
            self.aktif = False
            return

        while self.aktif:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            
            frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]
            
            # Yerel kamera RGB okuduğu için algoritma uyumluluğu adına Gri tona çeviriyoruz.
            gri_ton = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            self._ekrana_goruntu_gonder(gri_ton)
            self._yuz_ve_postur_analizi(gri_ton, fw, fh)
            time.sleep(0.03) # ~30 FPS dengelemesi

        cap.release()

    def _ekrana_goruntu_gonder(self, gri_matris):
        """ Ham gri matrisi PIL formatına evirip CustomTkinter nesnesine asenkron enjekte eder. """
        if self.arayuz:
            try:
                img_pil = Image.fromarray(gri_matris)
                img_ctk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(300, 200))
                # GUI thread çökmesini önlemek için .after metodu ile güvenli enjeksiyon yapıyoruz.
                self.arayuz.pencere.after(0, lambda: self.arayuz.kamera_guncelle(img_ctk))
            except Exception as e:
                print(f"[UYARI] Kare arayüze gönderilemedi: {e}")

    def _yuz_ve_postur_analizi(self, gri_ton, fw, fh):
        """ Ergonomik Postür ve Odak Değerlendirme Algoritması """
        yuzler = self.yuz_bulucu.detectMultiScale(gri_ton, scaleFactor=1.3, minNeighbors=5, minSize=(40, 40))
        
        if len(yuzler) > 0:
            # Ekranda yüz varsa yokluk sayacını hızla sıfıra doğru çekiyoruz.
            self.yokluk_sayac = max(0, self.yokluk_sayac - 5)
            (x, y, w, h) = yuzler[0]
            
            # İlk açılışta kullanıcının dik oturduğu varsayılarak referans Y noktası kalibre edilir.
            if self.referans_y is None:
                self.referans_y = y
                print(f"[KAMERA] Postür kalibrasyonu yapıldı. İdeal Referans Y Koordinatı: {y}")
            
            # Eğer kullanıcının yüz koordinatı (Y), referans noktasından 45 pikselden fazla aşağı düşerse
            # bu durum omurganın eğildiğine (kamburluk) işaret eder.
            if y > self.referans_y + 45:
                self.kambur_sayac += 1
                if self.kambur_sayac > 25: # Yanlış alarmları önlemek için ardışık 25 frame toleransı
                    print("[KAMERA_UYARI] Kambur oturuş algılandı! Telemetri güncelleniyor.")
                    if self.arayuz:
                        self.arayuz.pencere.after(0, lambda: self.arayuz.kambur_sayisi.set(self.arayuz.kambur_sayisi.get() + 1))
                        self.arayuz.ekrana_yaz("Robi", "Duruş Analizi: Kambur oturduğun gözlemlendi, lütfen postürünü düzelt.")
                    
                    self.kambur_sayac = 0
                    time.sleep(6) # Kullanıcıya düzelmesi için 6 saniye süre verilir (Spam engelleme)
            else:
                self.kambur_sayac = max(0, self.kambur_sayac - 1)
        else:
            # Ekranda yüz bulunamadığı her frame için yokluk sayacı artar.
            self.yokluk_sayac += 1
            if self.yokluk_sayac > 120: # Yaklaşık 4-5 saniye masadan uzaklaşma durumu
                print("[KAMERA_UYARI] Masadan kaytarma durumu saptandı.")
                if self.arayuz:
                    self.arayuz.pencere.after(0, lambda: self.arayuz.odak_kaybi_sayisi.set(self.arayuz.odak_kaybi_sayisi.get() + 1))
                    self.arayuz.ekrana_yaz("Robi", "Odak Analizi: Masadan kaytarma veya odak kaybı durumu saptandı.")
                
                self.yokluk_sayac = 0  
                time.sleep(6)  

    def durdur(self):
        self.aktif = False
        print("[KAMERA] Görüntü işleme motoru kapatıldı.")