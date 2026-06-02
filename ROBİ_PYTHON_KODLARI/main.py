# =============================================================================
# 🚀 ROBİ MASAÜSTÜ ASİSTAN SİSTEMİ - ANA GİRİŞ NOKTASI (main.py)
# =============================================================================
# Bu dosya; donanım haberleşmesi, yapay zeka motoru, grafik arayüz, zamanlayıcı
# takvim ve görüntü işleme modüllerini tek bir çatı altında başlatır ve yönetir.

from haberlesme import SeriHaberlesme
from yapay_zeka import LLMMotoru
from takvim import TakvimYoneticisi
from arayuz import RobiArayuz
from goruntu_isleme import GoruntuIslemeMotoru  

def sistemi_baslat():
    print("--- ROBİ SİSTEMİ ANALİTİK PANEL (VİZYON + GRAFİK) MODUNDA BAŞLATILIYOR ---\n")
    
    # Yerel ağ üzerinde socket sunucusunu 8080 portunda ayağa kaldırıyoruz.
    # Bu sunucu ESP32-S3 ana kontrolcü kartının bağlanmasını bekleyecek.
    robi_donanim = SeriHaberlesme(port=8080) 
    
    # LLM (Büyük Dil Modeli) motorunu instantiate ediyoruz.
    robi_zeka = LLMMotoru()
    
    # Yapay zeka motoruna donanım referansını veriyoruz ki ürettiği komutları fiziksel olarak iletebilsin.
    robi_zeka.donanim = robi_donanim
    
    # CustomTkinter tabanlı GUI (Gelişmiş Grafik Arayüz) nesnesini oluşturuyoruz.
    uygulama = RobiArayuz(robi_donanim, robi_zeka)
    
    # Donanım haberleşme katmanına arayüz referansını bağlıyoruz.
    # Böylece ESP32'den gelen donanım sinyalleri (örn: WAKE veya POSTURE_BAD) arayüze anlık yansıyabilecek.
    robi_donanim.arayuz = uygulama
    
    # Arka planda zaman duyarlı rutinleri (örn: spor hatırlatması) kontrol eden takvim motorunu başlatıyoruz.
    robi_takvim = TakvimYoneticisi(robi_donanim, robi_zeka)
    robi_takvim.baslat()
    
    # ESP32-CAM kartının yerel ağdaki video stream URL adresi.
    # GitHub Güvenliği: Ham IP adresi yerine konfigüre edilebilir yer tutucu bırakılmıştır.
    esp32_cam_url = "http://<YOUR_ESP32_CAM_IP>:81/stream" 
    
    # Görüntü işleme motorunu (Yüz ve Postür analizi yapan OpenCV katmanı) başlatıyoruz.
    goruntu_motoru = GoruntuIslemeMotoru(kamera_id=esp32_cam_url, robi_donanim=robi_donanim, arayuz_referansi=uygulama)
    goruntu_motoru.baslat()
    
    try:
        # Ana GUI döngüsünü (Main Loop) tetikliyoruz. Bu satır uygulama kapatılana kadar thread'i bloke eder.
        uygulama.calistir() 
    except KeyboardInterrupt:
        print("Sistem kullanıcı isteğiyle kapatılıyor.")
    finally:
        # Uygulama kapatıldığında açık soketlerin ve kamera thread'lerinin güvenli bir şekilde sonlandırılması.
        print("\n--- SİSTEM GÜVENLİ ŞEKİLDE KAPATILIYOR ---")
        goruntu_motoru.durdur()
        robi_donanim.kapat()

if __name__ == "__main__":
    sistemi_baslat()