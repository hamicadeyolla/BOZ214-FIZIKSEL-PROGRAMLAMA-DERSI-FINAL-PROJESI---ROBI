# =============================================================================
# 📅 ARKA PLAN RUTİN KONTROL VE ZAMANLAYICI MÜHENDİSLİĞİ (takvim.py)
# =============================================================================
# Bu sınıf, arka planda sonsuz bir daemon thread koşturarak saati kontrol eder.
# Belirlenen zaman dilimi geldiğinde (örn: Akşam 19:00 idman vakti) robotun 
# duygu durumunu ve kullanıcının rutinlerini yönetir.

import time
import threading
from datetime import datetime

class TakvimYoneticisi:
    def __init__(self, robi_donanim, robi_zeka):
        self.donanim = robi_donanim
        self.zeka = robi_zeka
        self.aktif = True
        self.idman_gunu_sayaci = 1  # 5 günlük döngüsel takip algoritması
        self.son_tetiklenen_dakika = ""  # Aynı dakika içinde mükerrer tetiklenmeyi önleme kilidi

    def gunluk_rutin_kontrol(self):
        print("[TAKVİM] Arka plan zamanlayıcısı başlatıldı.")
        while self.aktif:
            # Bilgisayarın yerel saatini HH:MM formatında çekiyoruz.
            su_an = datetime.now().strftime("%H:%M")
            
            # Akşam saat 19:00 kontrol mekanizması
            if su_an == "19:00" and self.son_tetiklenen_dakika != su_an:
                print("\n[TAKVİM TETİKLENDİ] İdman Vakti Kontrolü!")
                self.son_tetiklenen_dakika = su_an  
                
                # Döngüsel algoritma: İlk 3 gün antrenman, sonraki 2 gün dinlenme fazı
                if self.idman_gunu_sayaci <= 3:
                    mesaj = "Bugün idman günün. O hipertrofi antrenmanını ekersen sabaha kadar alarm çalarım!"
                    self.donanim.komut_gonder("E:ANGRY") # Robi OLED ekranı sinirli moda geçer
                else:
                    mesaj = "Bugün dinlenme günün. Kasların toparlanması lazım, git biraz yat."
                    self.donanim.komut_gonder("E:SMILE") # Robi mutlu moda geçer
                
                print(f"Robi: {mesaj}")
                self.donanim.komut_gonder("T:120") # Boyun düz bakış pozisyonuna kalibre edilir
                
                # Sayaç yönetimi (1-5 arası döngü)
                self.idman_gunu_sayaci += 1
                if self.idman_gunu_sayaci > 5:
                    self.idman_gunu_sayaci = 1
                
            time.sleep(10) # İşlemciyi yormamak adına her 10 saniyede bir saati kontrol eder

    def baslat(self):
        # Zamanlayıcıyı ana thread'den koparıp arka plan işçisi olarak çalıştırıyoruz.
        takvim_thread = threading.Thread(target=self.gunluk_rutin_kontrol)
        takvim_thread.daemon = True
        takvim_thread.start()