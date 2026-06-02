# =============================================================================
# 💻 MODERN KONTROL PANELİ VE GRAFİKSEL KULLANICI ARAYÜZÜ (arayuz.py)
# =============================================================================
# Bu sınıf, CustomTkinter kütüphanesi kullanarak koyu tema odaklı, asenkron,
# canlı telemetri grafiklerine sahip (Matplotlib entegrasyonlu) yönetim panelini kurar.

import customtkinter as ctk
import tkinter as tk  
import threading
import speech_recognition as sr
import time
import webbrowser
import urllib.parse
from PIL import Image

import matplotlib
matplotlib.use("TkAgg") # Tkinter backend'i ile matplotlib entegrasyonu
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class RobiArayuz:
    def __init__(self, robi_donanim, robi_zeka):
        self.donanim = robi_donanim
        self.zeka = robi_zeka
        
        self.pencere = ctk.CTk()
        self.pencere.title("🤖 Robi Master Control Dashboard")
        self.pencere.geometry("1100x620")
        self.pencere.minsize(1050, 580)
        
        # Dinamik Değişken Tanımlamaları (Arayüz kartlarına bağlıdır)
        self.kambur_sayisi = ctk.IntVar(value=0)
        self.odak_kaybi_sayisi = ctk.IntVar(value=0)
        self.robi_durum_str = ctk.StringVar(value="GÖZLEMLİYOR 👁️")
        
        # Gerçek Zamanlı Matplotlib Çizimi İçin Zaman Serisi Veri Depoları
        self.grafik_sure = [0]
        self.grafik_kambur = [0]
        self.grafik_kaytarma = [0]
        self.baslangic_zamani = time.time()

        # -------------------------------------------------------------
        # 1. SOL PANEL: SİSTEM TELEMETRİSİ VE DONANIM OVERRIDE
        # -------------------------------------------------------------
        self.sol_panel = ctk.CTkFrame(self.pencere, width=260, corner_radius=15, fg_color="#1e1f22")
        self.sol_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=10, pady=15)
        self.sol_panel.pack_propagate(False)
        
        ctk.CTkLabel(self.sol_panel, text="ROBIDESK PANEL", font=ctk.CTkFont(family="Consolas", size=16, weight="bold"), text_color="#5865f2").pack(pady=(20, 15))
        
        ctk.CTkLabel(self.sol_panel, text="SİSTEM DURUMU", font=ctk.CTkFont(size=10, weight="bold"), text_color="#b9bbbe").pack(anchor="w", padx=20, pady=(10, 2))
        self.durum_karti = ctk.CTkLabel(self.sol_panel, textvariable=self.robi_durum_str, font=ctk.CTkFont(size=13, weight="bold"), text_color="#2ecc71", fg_color="#2b2d31", height=40, corner_radius=8)
        self.durum_karti.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        ctk.CTkLabel(self.sol_panel, text="CANLI TELEMETRİ VERİLERİ", font=ctk.CTkFont(size=10, weight="bold"), text_color="#b9bbbe").pack(anchor="w", padx=20, pady=(10, 2))
        
        kambur_card = ctk.CTkFrame(self.sol_panel, fg_color="#2b2d31", height=40, corner_radius=8)
        kambur_card.pack(fill=tk.X, padx=20, pady=4)
        kambur_card.pack_propagate(False)
        ctk.CTkLabel(kambur_card, text="Duruş Bozukluğu:", font=ctk.CTkFont(size=12), text_color="#dcddde").pack(side=tk.LEFT, padx=15)
        ctk.CTkLabel(kambur_card, textvariable=self.kambur_sayisi, font=ctk.CTkFont(size=14, weight="bold"), text_color="#e74c3c").pack(side=tk.RIGHT, padx=15)
        
        odak_card = ctk.CTkFrame(self.sol_panel, fg_color="#2b2d31", height=40, corner_radius=8)
        odak_card.pack(fill=tk.X, padx=20, pady=4)
        odak_card.pack_propagate(False)
        ctk.CTkLabel(odak_card, text="Kaytarma Algısı:", font=ctk.CTkFont(size=12), text_color="#dcddde").pack(side=tk.LEFT, padx=15)
        ctk.CTkLabel(odak_card, textvariable=self.odak_kaybi_sayisi, font=ctk.CTkFont(size=14, weight="bold"), text_color="#f1c40f").pack(side=tk.RIGHT, padx=15)
        
        ctk.CTkLabel(self.sol_panel, text="KAPSAMLI DONANIM OVERRIDE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#b9bbbe").pack(anchor="w", padx=20, pady=(20, 2))
        
        ctk.CTkLabel(self.sol_panel, text="OLED Duygu Durum Seçimi:", font=ctk.CTkFont(size=11), text_color="#dcddde").pack(anchor="w", padx=20, pady=(5, 2))
        self.duygu_combo = ctk.CTkComboBox(self.sol_panel, values=["NORMAL", "SAD", "ANGRY", "THINK", "SMILE", "SLEEP", "FOCUS", "WINK", "SUNNY", "RAINY", "SNOWY"], command=self._manuel_duygu_degis)
        self.duygu_combo.pack(fill=tk.X, padx=20, pady=2)
        self.duygu_combo.set("NORMAL")
        
        ctk.CTkLabel(self.sol_panel, text="Servo / Mekanik Konum Testi:", font=ctk.CTkFont(size=11), text_color="#dcddde").pack(anchor="w", padx=20, pady=(10, 2))
        # 🌟 Mekanik kısıtlara göre güncellenen 15'er derecelik güvenli servo test sınırları listesi
        self.servo_combo = ctk.CTkComboBox(self.sol_panel, values=["P:90 (Pan: Karşı)", "T:120 (Tilt: Düz)", "T:100 (Tilt: Yukarı)", "T:140 (Tilt: Aşağı)", "P:60 (Pan: Sağ)", "P:120 (Pan: Sol)", "A:SHOW (Animasyon Gösterisi)"], fg_color="#d35400", button_color="#e67e22", button_hover_color="#d35400", command=self._manuel_servo_degis)
        self.servo_combo.pack(fill=tk.X, padx=20, pady=2)
        self.servo_combo.set("P:90 (Pan: Karşı)")

        # -------------------------------------------------------------
        # 2. ORTA PANEL: ROBİ KAMERA AKIŞI VE VERİMLİLİK GRAFİĞİ
        # -------------------------------------------------------------
        self.orta_panel = ctk.CTkFrame(self.pencere, width=340, corner_radius=15, fg_color="#1e1f22")
        self.orta_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=15)
        self.orta_panel.pack_propagate(False)
        
        ctk.CTkLabel(self.orta_panel, text="ROBİ VİZYON & GRAFİK", font=ctk.CTkFont(size=14, weight="bold"), text_color="#2ecc71").pack(pady=(15, 5))
        
        ctk.CTkLabel(self.orta_panel, text="CANLI VİZYON AKIŞI", font=ctk.CTkFont(size=10, weight="bold"), text_color="#b9bbbe").pack(anchor="w", padx=20)
        self.kamera_etiketi = ctk.CTkLabel(self.orta_panel, text="Kamera Akışı Bekleniyor...", fg_color="#2b2d31", width=300, height=200, corner_radius=10)
        self.kamera_etiketi.pack(padx=20, pady=(2, 15))
        
        ctk.CTkLabel(self.orta_panel, text="ZAMANA BAĞLI VERİMLİLİK", font=ctk.CTkFont(size=10, weight="bold"), text_color="#b9bbbe").pack(anchor="w", padx=20)
        
        # Matplotlib Eksen ve Stil Yapılandırması (Koyu Tema Uyumu İçin Hex kodları verilmiştir)
        self.fig = Figure(figsize=(3.0, 2.0), dpi=100, facecolor='#1e1f22')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1f22')
        self.ax.tick_params(colors='#b9bbbe', labelsize=8)
        self.ax.set_xlabel("Süre (sn)", color='#b9bbbe', fontsize=8)
        self.ax.spines['bottom'].set_color('#4f545c')
        self.ax.spines['top'].set_color('#1e1f22')
        self.ax.spines['right'].set_color('#1e1f22')
        self.ax.spines['left'].set_color('#4f545c')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.orta_panel)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        self._grafik_tetikle() # Grafik çizim loop'unu başlatır

        # -------------------------------------------------------------
        # 3. SAĞ PANEL: AKILLI SOHBET ALANI
        # -------------------------------------------------------------
        self.sag_panel = ctk.CTkFrame(self.pencere, corner_radius=15, fg_color="#1e1f22")
        self.sag_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=15)
        
        self.sohbet_kutusu = ctk.CTkTextbox(self.sag_panel, font=ctk.CTkFont(family="Segoe UI", size=13), fg_color="#2b2d31", text_color="#dcddde", corner_radius=10, border_width=1, border_color="#202225")
        self.sohbet_kutusu.pack(fill=tk.BOTH, expand=True, padx=15, pady=(15, 10))
        self.sohbet_kutusu.configure(state="disabled")
        
        girdi_frame = ctk.CTkFrame(self.sag_panel, fg_color="transparent")
        girdi_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=(0, 15))
        
        self.mesaj_girisi = ctk.CTkEntry(girdi_frame, placeholder_text="Robi'ye bir şeyler söyle veya pano hatasını danış...", font=ctk.CTkFont(size=13), fg_color="#383a40", text_color="white", border_width=0, corner_radius=8, height=40)
        self.mesaj_girisi.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.mesaj_girisi.bind("<Return>", self.mesaj_gonder)
        
        self.gonder_butonu = ctk.CTkButton(girdi_frame, text="SÖYLE", font=ctk.CTkFont(size=12, weight="bold"), fg_color="#5865f2", hover_color="#4752c4", width=90, height=40, corner_radius=8, command=self.mesaj_gonder)
        self.gonder_butonu.pack(side=tk.RIGHT)
        
        self.ekrana_yaz("Sistem", "Gelişmiş Analitik Dashboard aktif. Veri ve video yolları dinleniyor.")

    def ekrana_yaz(self, gonderen, mesaj):
        """ Log ve konuşma geçmişini thread-safe bir şekilde ekrana formatlar. """
        self.sohbet_kutusu.configure(state="normal")
        if gonderen == "Sen": prefix = "👤 Sen: "
        elif gonderen == "Robi": prefix = "🤖 Robi: "
        else: prefix = "⚙️ Sistem: "
            
        self.sohbet_kutusu.insert(ctk.END, f"{prefix}{mesaj}\n\n")
        self.sohbet_kutusu.see(ctk.END) # Scroll'u en alta kaydırır
        self.sohbet_kutusu.configure(state="disabled")

    def mesaj_gonder(self, event=None):
        """ Girdi kutusundaki veriyi alıp API thread'ine aktarır. """
        mesaj = self.mesaj_girisi.get()
        if not mesaj.strip(): return
        
        self.mesaj_girisi.delete(0, tk.END)
        self.ekrana_yaz("Sen", mesaj)
        
        self.robi_durum_str.set("DÜŞÜNÜYOR... 🤔")
        self.durum_karti.configure(text_color="#f1c40f")
        self.donanim.komut_gonder("E:THINK")
        
        # Ağ istekleri GUI'yi dondurmasın diye işlemi işçi (worker) thread'e taşıyoruz.
        thread = threading.Thread(target=self._zeka_islem_thread, args=(mesaj,))
        thread.start()

    def kamera_guncelle(self, ctk_img):
        """ Görüntü işleme motorundan gelen kareleri ekranda render eder. """
        self.kamera_etiketi.configure(image=ctk_img, text="")

    def _grafik_tetikle(self):
        """ Matplotlib Zaman Serisi Çizim Döngüsü (Her saniye yenilenir) """
        if not hasattr(self, 'pencere'): return
        
        gecen_sure = int(time.time() - self.baslangic_zamani)
        self.grafik_sure.append(gecen_sure)
        self.grafik_kambur.append(self.kambur_sayisi.get())
        self.grafik_kaytarma.append(self.odak_kaybi_sayisi.get())
        
        # Grafiğin yığılmasını önlemek için son 60 saniyelik veriyi kaydıran pencere (Sliding Window)
        if len(self.grafik_sure) > 60:
            self.grafik_sure.pop(0)
            self.grafik_kambur.pop(0)
            self.grafik_kaytarma.pop(0)
            
        self.ax.clear()
        self.ax.set_facecolor('#1e1f22')
        self.ax.tick_params(colors='#b9bbbe', labelsize=8)
        self.ax.set_xlabel("Süre (sn)", color='#b9bbbe', fontsize=8)
        
        # Çizgilerin matris verileri ile beslenmesi
        self.ax.plot(self.grafik_sure, self.grafik_kambur, color='#e74c3c', label='Kambur', linewidth=2)
        self.ax.plot(self.grafik_sure, self.grafik_kaytarma, color='#f1c40f', label='Kaytarma', linewidth=2)
        self.ax.legend(facecolor='#2b2d31', edgecolor='none', labelcolor='#dcddde', loc='upper left', fontsize=7)
        
        self.canvas.draw()
        self.pencere.after(1000, self._grafik_tetikle) # 1000 ms sonra öz-yinelemeli çağrı

    def _manuel_duygu_degis(self, secim):
        self.donanim.komut_gonder(f"E:{secim}")

    def _manuel_servo_degis(self, secim):
        """ Arayüzdeki combo-box'tan seçilen manuel test komutlarını ayrıştırır. """
        temiz_komut = secim.split(" ")[0]
        if temiz_komut == "A:SHOW":
            # Bloklama yapmaması için animasyon şovu arka planda asenkron çalıştırılır
            threading.Thread(target=self._animasyon_gosterisi_tetikle, daemon=True).start()
        else:
            self.donanim.komut_gonder(temiz_komut)

    def _animasyon_gosterisi_tetikle(self):
        """ Merkezi Animasyon Makro Motoru """
        print("[ANİMASYON] Manuel Gösteri Makrosu Başlatıldı.")
        # P:60 ve P:120 yeni donanım limitleri baz alınarak oluşturulmuş servo koreografisi
        gosteri_serisi = ["E:FOCUS", "P:60", "P:120", "T:140", "T:100", "P:90", "T:120", "E:NORMAL"]
        for s_komut in gosteri_serisi:
            self.donanim.komut_gonder(s_komut)
            time.sleep(0.7)

    def sesli_soru_tetikle(self):
        """ ESP32-S3'ten uyanma kelimesi (Hey Robi) geldiğinde mikrofonu dinleme moduna alır. """
        if hasattr(self, 'dinliyor') and self.dinliyor:
            return 
            
        self.dinliyor = True
        self.robi_durum_str.set("DİNLEYİCİ AKTİF 🎙️")
        self.durum_karti.configure(text_color="#3498db")
        self.ekrana_yaz("Sistem", "Robi seni dinliyor...")
        
        thread = threading.Thread(target=self._PC_mikrofon_dinleme_thread)
        thread.start()

    def _PC_mikrofon_dinleme_thread(self):
        """ PC Mikrofonu üzerinden Google Speech Recognition (STT) Döngüsü """
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True 
        r.dynamic_energy_adjustment_damping = 0.15
        r.dynamic_energy_ratio = 1.5
        r.pause_threshold = 1.3 # Kullanıcı durakladığında kesilmemesi için ideal eşik
        
        with sr.Microphone() as source:
            try:
                r.adjust_for_ambient_noise(source, duration=0.4) # Ortam gürültü kalibrasyonu
                audio = r.listen(source, timeout=6, phrase_time_limit=12)
                self.robi_durum_str.set("SES İŞLENİYOR... 🛠️")
                soru_metni = r.recognize_google(audio, language="tr-TR")
                
                self.pencere.after(0, lambda: self.donanim.komut_gonder("E:THINK"))
                self.pencere.after(0, lambda: self.ekrana_yaz("Sen", soru_metni))
                self._zeka_islem_thread(soru_metni)
                
            except sr.WaitTimeoutError:
                self.pencere.after(0, lambda: self.ekrana_yaz("Robi", "Seni dinledim ama bir şey söylemedin."))
                self.pencere.after(0, lambda: self.donanim.komut_gonder("E:NORMAL"))
            except Exception as e:
                print(f"[STT HATASI] Ses metne çevrilemedi: {e}")
                self.pencere.after(0, lambda: self.donanim.komut_gonder("E:NORMAL"))
            finally:
                self.pencere.after(0, lambda: self.robi_durum_str.set("GÖZLEMLİYOR 👁️"))
                self.pencere.after(0, lambda: self.durum_karti.configure(text_color="#2ecc71"))
                self.dinliyor = False

    def _zeka_islem_thread(self, mesaj):
        """ LLM'den gelen cevap paketlerini ve aksiyon kuyruklarını sırayla icra eden thread. """
        self.robi_durum_str.set("DÜŞÜNÜYOR... 🤔")
        self.durum_karti.configure(text_color="#f1c40f")
        
        temiz_cevap, aksiyon_kuyrugu = self.zeka.cevap_uret(mesaj)
        self.pencere.after(0, lambda: self.ekrana_yaz("Robi", temiz_cevap))
        
        # Kuyruktaki aksiyonların sırasıyla donanıma kablosuz iletilmesi
        for aksiyon in aksiyon_kuyrugu:
            if aksiyon["type"] == "cmd":
                cmd_val = aksiyon["value"]
                
                if cmd_val == "A:SHOW":
                    self._animasyon_gosterisi_tetikle()
                        
                elif cmd_val.startswith("A:MUSIC:"):
                    sarki_sorgusu = cmd_val.replace("A:MUSIC:", "").strip()
                    if sarki_sorgusu:
                        print(f"[SPOTIFY] Şarkı yerel uygulamadan aranıyor: {sarki_sorgusu}")
                        encoded_sorgu = urllib.parse.quote(sarki_sorgusu)
                        webbrowser.open(f"spotify:search:{encoded_sorgu}") # Spotify URI Protokolü
                        
                else:
                    self.donanim.komut_gonder(cmd_val)
                    time.sleep(0.15) # Servo aşırı yüklenmesini önlemek için küçük bekleme
            
            elif aksiyon["type"] == "text":
                self.robi_durum_str.set("KONUŞUYOR... 🗣️")
                self.durum_karti.configure(text_color="#2ecc71")
                self.zeka.sesli_oku_senkron(aksiyon["value"])
        
        # İşlem tamamlanınca sistemi kararlı gözlem moduna geri çekiyoruz.
        self.pencere.after(0, lambda: self.robi_durum_str.set("GÖZLEMLİYOR 👁️"))
        self.pencere.after(0, lambda: self.durum_karti.configure(text_color="#2ecc71"))
        self.pencere.after(0, lambda: self.donanim.komut_gonder("E:NORMAL"))

    def calistir(self):
        self.pencere.mainloop()