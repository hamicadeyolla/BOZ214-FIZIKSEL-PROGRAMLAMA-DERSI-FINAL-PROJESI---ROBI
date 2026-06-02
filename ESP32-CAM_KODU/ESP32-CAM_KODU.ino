// =============================================================================
// 📸 ESP32-CAM GÜVENLİ VE OPTİMİZE VİZYON SÜRÜCÜSÜ
// =============================================================================
// Bu yazılım, Robi'nin kafa modülündeki OV2640 kamera sensörünü kontrol eder.
// Isınma, yüksek akım sıçramaları ve çökme (Brownout) risklerini engellemek için
// gömülü düzeyde voltaj ve termal frekans regülasyon önlemleri barındırır.

#include "esp_camera.h" // Espressif Resmi Kamera Donanım Sürücü Kütüphanesi
#include <WiFi.h>

// GÜVENLİK NOTU: Yerel Wi-Fi ağ bilgileri sızıntıyı önlemek amacıyla maskelenmiştir.
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// AI-THINKER Üretici Kartı Donanmsal Pin Matrisi (Pin Mapping)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1  // Donanımsal reset pini kullanılmıyor
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       36
#define Y6_GPIO_NUM       39
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

WiFiServer server(81); // Python OpenCV modülünün bağlanacağı video yayın TCP portu

// =============================================================================
// 🚀 3. SİSTEM GÖMÜLÜ REGLASYON KURULUMU (SETUP)
// =============================================================================
void setup() {
    // 📉 TERMAL OPTİMİZASYON 1: ESP32-CAM kartının fabrikasyon CPU saat frekansını
    // 240MHz'den 160MHz'e düşürüyoruz. Bu hamle, dar 3D gövde içindeki işlemcinin
    // aşırı ısınarak kilitlenmesini ve termal kararsızlığa girmesini kesin olarak engeller.
    setCpuFrequencyMhz(160);
    
    Serial.begin(115200);
    Serial.printf("\n=== ROBI GÜVENLİ VİZYON MODU BAŞLATILIYOR ===\n");
    
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;   config.pin_d1 = Y3_GPIO_NUM;   config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;   config.pin_d4 = Y6_GPIO_NUM;   config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;   config.pin_d7 = Y9_GPIO_NUM;   config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM; config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM; config.pin_sscb_scl = SIOC_GPIO_NUM; config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;

    // Sinyal Kalitesi Güvencesi: İnce jumper kablolardaki kapasitif parazitleri
    // ve frame kayıplarını sıfırlamak için XCLK frekansı kararlı 10MHz'e sabitlenmiştir.
    config.xclk_freq_hz = 10000000;
    
    // 👁️ DÜŞÜK BELLEK VE SOKET PERFORMANS OPTİMİZASYONU
    // Python tarafındaki OpenCV yüz ve postür takibi motoru renk bilgisine ihtiyaç duymaz.
    // Pixel formatını GRAYSCALE seçerek ağ trafiğini ve RAM yükünü anında 3 kat hafifletiyoruz.
    config.pixel_format = PIXFORMAT_GRAYSCALE; 
    config.frame_size = FRAMESIZE_QVGA;        // 320x240 ideal analitik işlem çözünürlüğü
    config.fb_count = 1;                       // Gecikmeyi (Latency) sıfıra indiren tekil kare arabelleği

    // Kamera alt sisteminin donanımsal olarak çalıştırılması
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[HATA] Kamera donanımı başlatılamadı: 0x%x\n", err);
        return;
    }
    Serial.println("[BAŞARILI] OV2640 Kamera Gri Sensör Modunda Aktif.");

    // 📉 ELEKTRİKSEL OPTİMİZASYON 2: Wi-Fi verici anten gücünü (Tx Power) maksimumdan (19.5dBm)
    // 11dBm seviyesine limitliyoruz. Bu hayati hamle, kamera sensörü tetiklendiği an RF devrelerinin
    // çektiği ani yüksek akım sıçramalarını (RF Peak Current) dizginler ve kartın voltaj düşümünden 
    // dolayı reset atmasını (Brownout) tamamen engeller.
    WiFi.setTxPower(WIFI_POWER_11dBm);
    
    Serial.print("[Wi-Fi] Ağa bağlanılıyor: ");
    Serial.println(ssid);
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    server.begin(); // TCP Video yayın soket sunucusunu başlat
    Serial.println("\n[Wi-Fi BAŞARILI] Robi Kamera Sunucusu Bağlantıya Hazır!");
    Serial.print("[BİLGİ] ESP32-CAM Yerel IP Adresi: ");
    Serial.println(WiFi.localIP());
}

// =============================================================================
// 🔄 4. ANA DÖNGÜ VE STREAM AKIŞ YÖNETİMİ (LOOP)
// =============================================================================
void loop() {
    // Python backend uygulamasından gelecek olan soket bağlantı isteğini bekle
    WiFiClient client = server.available();

    if (client) {
        Serial.println("[BAĞLANTI] Python Dashboard bağlandı, canlı yayın akışı aktarılıyor.");

        // İstemci bağlı kaldığı sürece döngü içerisinde ham pikselleri bas
        while (client.connected()) {
            camera_fb_t * fb = esp_camera_fb_get(); // Sensörden anlık kareyi yakala
            if (!fb) {
                Serial.println("[HATA] Kameradan kare alınamadı!");
                continue;
            }

            // Ağ Verimlilik Optimizasyonu: JPEG sıkıştırma (encode) işlem yüküne girilmeden
            // ham gri ton piksel bayt dizisi paket sarmalı olmadan doğrudan TCP soket hattına akıtılır.
            client.write(fb->buf, fb->len);

            // Donanımsal Bellek Yönetimi: Bellek sızıntılarını (Memory Leak) ve kartın kilitlenmesini
            // önlemek amacıyla işlenen kare arabelleği anında sisteme iade edilir.
            esp_camera_fb_return(fb);

            // 📉 AKIŞ OPTİMİZASYON 3: Her kare gönderiminin arasına bilinçli olarak 100ms dinlenme
            // koyarak akış hızını ~10 FPS seviyesinde dengeliyoruz. Bu sayede hem işlemcinin 
            // gövde içinde aşırı ısınması engellenir hem de evdeki Wi-Fi ağ trafiği rahatlar.
            delay(100);
        }
        Serial.println("[BAĞLANTI] Python Dashboard bağlantıyı kesti.");
    }
}