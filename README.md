# BOZ214-FIZIKSEL-PROGRAMLAMA-DERSI-FINAL-PROJESI---ROBI
Ergonomik Postür ve İş Akışı Takibi İçin Dağıtık Yapay Zekâ Destekli Masaüstü Robot Asistanı / Distributed Edge-Cloud AI-Powered Desktop Robot Assistant.

# 🤖 BOZ214 FİZİKSEL PROGRAMLAMA DERSİ FİNAL PROJESİ - BENİ OKU

* **Proje Adı:** Masaüstü Robot Asistan: RoboDesk (Robi)
* **Geliştiriciler:** Abdullah Şerefoğlu & Hamza Osman Erdoğan
* **Teslim Tarihi:** 02.06.2026

Bu dosya; Robi Masaüstü Asistanı projesinin kaynak kod yapısını, sistem gereksinimlerini, donanımsal optimizasyon detaylarını ve çalıştırma prosedürlerini içeren teknik kurulum kılavuzudur.

---

## 📁 1. TESLİM PAKETİ KLASÖR YAPISI

Ana teslim arşivi (`proje_kodlarım.zip`) şu bileşenlerden oluşmaktadır:

```text
├── 📁 ESP32-S3_ANA_KONTROLCU_KODU/  -> Uçta TinyML ve donanım yönetimini yapan C++ kodu.
├── 📁 ESP32-CAM_KODU/               -> OpenCV motoruna saf gri ton stream sağlayan C++ kodu.
├── 📁 python_kodlarım/              -> CustomTkinter GUI ve LLM multimodal analiz motoru.
│   ├── arayuz.py
│   ├── goruntu_isleme.py
│   ├── haberlesme.py
│   ├── main.py
│   ├── takvim.py
│   └── yapay_zeka.py
└── 📦 hey_robi.zip                   -> Edge Impulse üzerinde eğitilen TinyML uyanma modeli kütüphanesi.

🛠️ 2. DONANIM VE YAZILIM GEREKSİNİMLERİ
[Yazılımsal Gereksinimler]
Python 3.10+ sürümü

Arduino IDE (ESP32 Board Manager 2.X veya 3.X yüklü olmalıdır)

[Python Bağımlılıkları (Kütüphane Kurulumu)]
Python Dashboard'un kararlı çalışabilmesi için terminalde aşağıdaki komut çalıştırılarak gerekli kütüphaneler kurulmalıdır:

pip install customtkinter opencv-python matplotlib pygame requests edge-tts SpeechRecognition Pillow

🚀 3. ADIM ADIM KURULUM VE ÇALIŞTIRMA REHBERİ
ADIM 1: Edge AI (TinyML) Modelinin Arduino IDE'ye Dahil Edilmesi
Arduino IDE uygulamasını açın.

Taslak (Sketch) -> Kütüphane Ekle (Include Library) -> .ZIP Kütüphanesi Ekle (.ZIP Library) adımlarını takip edin.

Ana dizindeki hey_robi.zip dosyasını seçerek sisteme yükleyin.

Yükleme tamamlandığında kütüphane, Arduino IDE içerisinde entegre şekilde abdullahserr-project-1_inferencing adıyla görünecektir. Bu işlem "HeyRobi" uyanma modelini kodun derleme sürecine otomatik olarak dahil eder.

ADIM 2: Donanım Kodlarının Yüklenmesi ve Yerel Ağ Kalibrasyonu
ESP32-S3_ANA_KONTROLCU_KODU içerisindeki kaynak kodu Arduino IDE ile açın.

Kart Seçimi: "ESP32S3 Dev Module"

Kodun başındaki ssid ve password değişkenlerine yerel Wi-Fi bilgilerinizi girin.

host değişkenine Python uygulamasının çalışacağı bilgisayarın yerel IP adresini yazın ve kodu karta flaşlayın.

ESP32-CAM_KODU içerisindeki kaynak kodu Arduino IDE ile açın.

Kart Seçimi: "AI Thinker ESP32-CAM"

Yerel Wi-Fi bilgilerinizi girin ve kodu karta flaşlayın.

Seri port ekranından kartın aldığı IP adresini not edin.

ADIM 3: Python Dashboard Katmanının Yapılandırılması ve Başlatılması
python_kodlarım klasörünü açın.

main.py içerisindeki esp32_cam_url değişkenine, bir önceki adımda ESP32-CAM'in aldığı IP adresini şu formatta girin:

esp32_cam_url = "http://<CAM_IP_ADRESI>:81/stream"

Sistemin çevre değişkenlerine (Environment Variables) veya işletim sistemi terminaline GEMINI_API_KEY adıyla kendi geçerli Gemini API anahtarınızı tanımlayın.

main.py dosyasını çalıştırarak merkezi yönetim panelini tetikleyin:

python main.py

📉 4. GÖMÜLÜ SİSTEM VE MİMARİ OPTİMİZASYON NOTLARI
Projenin kararlılığını artırmak ve fiziksel kısıtları yönetmek amacıyla kod seviyesinde şu mühendislik önlemleri alınmıştır:

Termal ve Güç Yönetimi (ESP32-CAM): Kapalı 3D gövde içerisindeki ısınmayı ve anlık akım sıçramalarına bağlı çöküşleri (Brownout) engellemek için CPU frekansı 160MHz'e, Wi-Fi anten gücü (Tx Power) ise 11dBm seviyesine düşürülmüştür.

Ağ Trafiği Optimizasyonu: OpenCV tabanlı yüz ve postür analizi renk bilgisine ihtiyaç duymadığından, ESP32-CAM verileri GRAYSCALE (saf gri ton) modunda ve ağı yormayacak şekilde ~10 FPS'te akıtır.

Donanımsal Koruma (Auto-Detach): SG90 servo motorların hedef açıya ulaştıktan sonra pozisyonu korumaya çalışırken titremesini ve yüksek akım çekmesini önlemek amacıyla, hareket bitiminden 2 saniye sonra servo sinyalleri yazılımsal olarak kesilir.

Pürüzsüz İnterpolasyon Motoru: Robotun kafa hareketlerinin insansı ve akıcı olabilmesi için doğrusal interpolasyon algoritması kullanılmıştır; kafa anlık keskin dönüşler yerine hedef açıya yumuşayarak akar.

Veri Gizliliği: Sürekli dinleme yapan INMP441 mikrofonu uyanma kelimesini tamamen yerel (offline) olarak çözer; uyanma sinyali tetiklenmeden bilgisayara veya buluta hiçbir ses verisi aktarılmaz.

Not: Proje Raporu, Proje Videosu ve Mühendislik Tasarım Defteri (Notebook) final yönergesine uygun olarak diğer ilgili teslim alanlarına yüklenmiştir.

© 2026 Abdullah Şerefoğlu & Hamza Osman Erdoğan. Tüm Hakları Saklıdır.

Bu GitHub deposunda yer alan tüm yazılım kodları, donanım şemaları, metinler ve 
görsel materyaller telif hakkı koruması altındadır. Yazarların yazılı izni olmaksızın 
bu kodların tamamı veya bir kısmı kopyalanamaz, dağıtılamaz, ticari veya ticari olmayan 
projelerde kaynak gösterilerek dahi kullanılamaz, değiştirilemez veya türetilemez.
