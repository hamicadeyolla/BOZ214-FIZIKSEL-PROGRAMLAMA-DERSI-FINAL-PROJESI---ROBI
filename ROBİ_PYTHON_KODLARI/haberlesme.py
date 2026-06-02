# =============================================================================
# 🌐 KABLOSUZ WI-FI TCP SOCKET SERVER KATMANI (haberlesme.py)
# =============================================================================
# Bu sınıf, ESP32-S3 mimarisi ile çift yönlü (Full-Duplex) veri transferi kurar.
# Python backend tarafında bir TCP sunucu açarak robottan gelen uyanma kelimesi (WAKE)
# ve donanım sensörü (POSTURE_BAD) verilerini dinler, robota ses ve servo paketi basar.

import socket
import threading
import time

class SeriHaberlesme:
    def __init__(self, port=8080, arayuz_referansi=None):
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.simulasyon_modu = False
        self.arayuz = arayuz_referansi
        self.aktif = True
        
        self.baglan()

    def baglan(self):
        """ Belirtilen port üzerinde ham TCP soket sunucusunu ayağa kaldırır. """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Portun çakışmasını engellemek için SO_REUSEADDR bayrağını aktif ediyoruz.
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 0.0.0.0 verilerek yerel ağdaki tüm bağdaştırıcılar (Ethernet, Wi-Fi) üzerinden dinleme açılır.
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(1)
            self.simulasyon_modu = False
            print(f"[HABERLEŞME] TCP Soket Sunucusu {self.port} portunda başlatıldı. ESP32-S3 bağlantısı bekleniyor...")
            
            # Bağlantı isteklerini dinleyen thread'i arka planda koşturuyoruz.
            self.baglanti_thread = threading.Thread(target=self._baglanti_kabul_et, daemon=True)
            self.baglanti_thread.start()
        except Exception as e:
            # Herhangi bir port hatasında sistemin çökmemesi için korumalı Simülasyon Modu devreye girer.
            self.simulasyon_modu = True
            print(f"[UYARI] Soket sunucusu başlatılamadı. Otomatik SİMÜLASYON MODU devreye alındı. (Hata: {e})")

    def _baglanti_kabul_et(self):
        """ Donanımdan gelen el sıkışma (Handshake) isteklerini kabul eden döngü. """
        while self.aktif:
            try:
                client_sock, addr = self.server_socket.accept()
                self.client_socket = client_sock
                print(f"[HABERLEŞME] ESP32-S3 robotu başarıyla bağlandı! Cihaz Bağlantısı Sağlandı.")
                
                # Cihaz bağlandığı an robottan gelecek sinyalleri yakalayacak dinleme thread'ini tetikliyoruz.
                self.dinleme_thread = threading.Thread(target=self.arka_plan_dinle, daemon=True)
                self.dinleme_thread.start()
            except Exception as e:
                if not self.aktif: break
                print(f"[HATA] Bağlantı kabul edilirken bir hata oluştu: {e}")
                time.sleep(2)

    def komut_gonder(self, komut):
        """ Karşı taraftaki ESP32-S3 karta string tabanlı mimik/servo komutu gönderir. """
        if self.client_socket:
            try:
                # ESP32 tarafındaki readStringUntil('\n') yapısı ile uyumlu olması için satır sonu ekliyoruz[cite: 112].
                self.client_socket.sendall(f"{komut}\n".encode('utf-8'))
                print(f"[-> Wi-Fi GİDEN] {komut}")
            except Exception as e:
                print(f"[HATA] Komut kablosuz ağ üzerinden gönderilemedi: {e}")
                self.client_socket = None
        elif self.simulasyon_modu:
            print(f"[SİMÜLASYON -> ESP32'YE GİDEN SANAL KOMUT] {komut}")
        else:
            print("[HATA] ESP32-S3 bağlı değil, komut iletilemedi.")

    def ses_gonder(self, pcm_data):
        """ Ham PCM Ses Verilerini Protokol Başlığı (Header) İle Paketleyip Wi-Fi'dan Basar """
        if self.client_socket:
            try:
                import pygame
                freq, fmt, channels = pygame.mixer.get_init()
                
                # ESP32'nin sesin boyutunu, frekansını ve kanal yapısını bilmesi için protokol başlığı üretiyoruz[cite: 368].
                header = f"AUDIO:{len(pcm_data)}:{freq}:{channels}\n"
                self.client_socket.sendall(header.encode('utf-8')) # Önce başlık verisi
                self.client_socket.sendall(pcm_data) # Hemen ardından ham ses bayt dizisi
                print(f"[-> Wi-Fi SES] {len(pcm_data)} bayt ({freq}Hz, {channels} Kanal) veri Robi'ye uyarlandı.")
            except Exception as e:
                print(f"[HATA] Ses verisi kablosuz ağdan gönderilemedi: {e}")
                self.client_socket = None

    def arka_plan_dinle(self):
        """ 📥 ESP32-S3 Kartından Gelen Telemetri ve Tetikleme Sinyallerini Dinleyen Motor """
        print("[HABERLEŞME] Arka plan Wi-Fi soket dinleyicisi aktif.")
        tam_veri = ""
        while self.client_socket:
            try:
                veri = self.client_socket.recv(1024).decode('utf-8')
                if not veri:
                    print("[HABERLEŞME] ESP32-S3 bağlantıyı kapattı.")
                    self.client_socket = None
                    break
                
                tam_veri += veri
                # Buffer'daki verileri satır satır bölerek paket kaybını önlüyoruz.
                while "\n" in tam_veri:
                    satir, tam_veri = tam_veri.split("\n", 1)
                    gelen_veri = satir.strip()
                    if not gelen_veri: continue
                    
                    print(f"[<- Wi-Fi GELEN SİNYAL] {gelen_veri}")
                    
                    if gelen_veri == "WAKE":
                        # ESP32 üzerindeki Edge Impulse yapay zekası kelimeyi çözdü, PC'deki arayüz tetiklenir[cite: 226, 229].
                        print("[ROBİ UYANDI] Uyanma kelimesi donanım tarafından tetiklendi.")
                        if self.arayuz:
                            self.arayuz.pencere.after(0, self.arayuz.sesli_soru_tetikle)
                            
                    elif gelen_veri == "POSTURE_BAD":
                        # Robotun üzerindeki fiziksel MPU6050/Sensör yapısı kamburluk algıladı sinyali.
                        if self.arayuz:
                            self.arayuz.pencere.after(0, lambda: self.arayuz.kambur_sayisi.set(self.arayuz.kambur_sayisi.get() + 1))
                            self.arayuz.pencere.after(0, lambda: self.arayuz.ekrana_yaz("Robi", "Duruşunu hemen düzelt, donanım sensörlerim omurganı eğri algılıyor!"))
            except Exception as e:
                print(f"[DİNLEME HATASI] Veri okunurken hata oluştu: {e}")
                self.client_socket = None
                break
            time.sleep(0.01)

    def kapat(self):
        self.aktif = False
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        print("[HABERLEŞME] Soket sunucusu kapatıldı.")