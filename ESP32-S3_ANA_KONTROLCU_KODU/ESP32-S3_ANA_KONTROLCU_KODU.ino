// =============================================================================
// 🤖 ROBİ MASAÜSTÜ ASİSTAN SİSTEMİ - ESP32-S3 ANA KONTROL YAZILIMI
// =============================================================================
// Bu yazılım; Edge Impulse tabanlı TinyML uyanma kelimesi (Wake-Word) modelini uçta koşturur,
// Wi-Fi üzerinden Python Dashboard sunucusuna bağlanır, çift yönlü soket haberleşmesini yönetir,
// Python'dan gelen ham PCM ses dalgalarını I2S üzerinden MAX98357A amfiye basar ve 
// mekanik aşınmaları/titremeleri engelleyen pürüzsüz bir servo interpolasyon motoru içerir.

#include <abdullahserr-project-1_inferencing.h> // Edge Impulse TinyML Ses Sınıflandırma Kütüphanesi
#include <Arduino.h>
#include <WiFi.h>
#include <U8g2lib.h>     // SH1106 OLED Grafik Ekran Sürücü Kütüphanesi
#include <ESP32Servo.h>  // ESP32 Donanımsal Zamanlayıcı Uyumlu Servo Kütüphanesi
#include <driver/i2s.h>  // Ham Ses Giriş/Çıkış İşlemleri İçin Espressif I2S Sürücüsü

#ifdef U8X8_HAVE_HW_SPI
#include <SPI.h>         // Donanımsal SPI Haberleşme Protokolü Destek Katmanı
#endif

// =============================================================================
// 🌐 0. AĞ VE SOKET KONFİGÜRASYONU (NETWORK SETTINGS)
// =============================================================================
// GÜVENLİK NOTU: Yerel ağ bilgileri sızıntıyı önlemek amacıyla yer tutucularla maskelenmiştir.
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* host = "YOUR_PYTHON_SERVER_IP"; // Python Dashboard'un kurulu olduğu bilgisayarın yerel IP'si
const uint16_t port = 8080;                  // Python Seri Haberleşme modülünün dinlediği TCP portu

WiFiClient client;                           // TCP bağlantı yönetim nesnesi
unsigned long sonBaglantiDenemesi = 0;       // Non-blocking bağlantı kontrolü için zaman damgası
const long baglantiAraligi = 5000;           // Ağ kopması durumunda her 5 saniyede bir yeniden bağlanma denemesi

// =============================================================================
// 📌 1. DONANIM PİN MİMARİSİ TANIMLAMALARI (HARDWARE PIN MAP)
// =============================================================================
// 1.3 inç 7-Pin SH1106 OLED Ekran SPI Bağlantı Haritası
#define OLED_CLK   36
#define OLED_MOSI  35
#define OLED_CS     2
#define OLED_DC    42
#define OLED_RST    1
// Yazılımsal SPI sarmalı ile ekran nesnesinin ayağa kaldırılması
U8G2_SH1106_128X64_NONAME_F_4W_SW_SPI u8g2(U8G2_R0, OLED_CLK, OLED_MOSI, OLED_CS, OLED_DC, OLED_RST);

// 2 Eksenli Boyun Mekanizması Servo Sürücü Pinleri
Servo panServo;
Servo tiltServo;
#define PAN_PIN  4  // Yatay eksen hareket motoru pini
#define TILT_PIN 5  // Dikey eksen hareket motoru pini

// INMP441 Dijital I2S Mikrofon Giriş Pin Haritası (Ses Alım Birimi)
#define I2S_WS   41  // Word Select (L/R Clock)
#define I2S_SD   40  // Serial Data Output
#define I2S_SCK  39  // Continuous Serial Clock (Bit Clock)
#define I2S_PORT I2S_NUM_0 // Giriş hattı için 0 numaralı donanımsal I2S birimi atanmıştır

// MAX98357A I2S Hoparlör Amplifikatörü Çıkış Pin Haritası (Ses Çıkış Birimi)
#define AMP_WS    18 // Word Select
#define AMP_SCK   17 // Bit Clock
#define AMP_SD    16 // Serial Data Input
#define AMP_PORT  I2S_NUM_1 // Çakışmaları önlemek için çıkış hattı 1 numaralı donanımsal I2S'e atanmıştır

// =============================================================================
// ⚙️ 2. SİSTEM DURUM DEĞİŞKENLERİ VE DURUM MAKİNESİ (STATE VARIABLES)
// =============================================================================
int currentEmotion = 5;               // İlk açılış modu: 5 (SLEEP - Uyku Modu)
unsigned long sonHareketZamani = 0;   // Servonun son hareket ettiği milisaniye verisi
const long serbestBirakmaGecikmesi = 2000; // Akım çekimini, vızıltıyı ve ısınmayı önlemek için servo de-attach gecikmesi
bool motorlarAktif = false;           // Servo motorların donanıma bağlılık (attach) durum takibi
unsigned long sonAktiviteZamani = 0;  // Robotun uykudan çıkmasını gerektiren son işlem zamanı
unsigned long sonAnimasyonZamani = 0; // OLED ekran tazeleme ve göz kırpma frekans zamanlayıcısı

// --- 🌟 İNTERPOLASYON (PÜRÜZSÜZ SERVO HAREKET ALGORİTMASI) ---
// Kafanın anlık keskin dönüşler yaparak donanıma zarar vermesini engeller.
// Hedef açıya (target) doğru anlık açıyı (current) adım adım yaklaştırarak sinematik akıcılık sağlar.
int targetPan = 90;
int targetTilt = 120;       // Kalibrasyon: Yeni mekanik sınırlara göre düz karşıya bakış referansı
float currentPan = 90.0;
float currentTilt = 120.0;
unsigned long sonServoGuncelleme = 0;
const int servoGuncellemeAraligi = 10; // İnterpolasyon hız ayarı (ms cinsinden adımsal döngü hızı)
const float servoAdimHizi = 2.0;       // Adım başına pürüzsüzlük derecesi (Yumuşaklık katsayısı)

// TinyML Yapay Zeka Ses Analiz Arabellekleri (Buffers)
int32_t i2s_raw_buffer[512]; // Mikrofon donanımından çekilen ham 32-bit veriler
int16_t inference_buffer[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE]; // Sinir ağı giriş boyutu kadar 16-bitlik pencere
static int32_t dc_running_avg = 0; // Ses sinyalindeki gürültüyü ve kaymayı sıfırlamak için DC bileşen filtresi
const int YENI_ORNEK_SAYISI = EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE / 4; // Sliding window (kayan pencere) yeni veri boyutu
const int KAYDIRILACAK_ORNEK_SAYISI = EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE - YENI_ORNEK_SAYISI;
bool ilkDolumYapildi = false;

// --- ✨ CANLI IDLE (BOŞTA KALMA - ORGANİK CANLILIK) MOTORU ---
// Robot hiçbir işlem yapmadığında heykel gibi kalmasın diye etrafa göz gezdirmesini,
// ara sıra göz kırpmasını sağlayan tamamen otonom çalışan durum makinesi (State Machine).
unsigned long sonIdleZamani = 0;
int idleState = 0; // 0: Merkez, 1: Sola bakış, 2: Sağa bakış, 3: Yukarı bakış, 4: Aşağı bakış, 5: Göz kırpma
unsigned long idleDurumBitisZamani = 0; // Seçilen anlık idle hareketinin ne kadar ekranda kalacağı
int idleXOffset = 0;                    // Geometrik göz çizimini kaydıran yatay ofset pikseli
int idleYOffset = 0;                    // Geometrik göz çizimini kaydıran dikey ofset pikseli
bool idleGozKirp = false;                // Göz kırpma animasyonu aktiflik bayrağı

// =============================================================================
// 🚀 4. SİSTEM İLK KURUMLUMU (SETUP)
// =============================================================================
void setup() {
    Serial.begin(115200); // Hata ayıklama logları için donanımsal UART hattı başlatılıyor
    wifiBaglan();         // Kablosuz ağ el sıkışması başlatılıyor
    
    u8g2.begin();
    u8g2.setFlipMode(1);  // Kasa montaj yönüne göre ekran görüntüsünü 180 derece ters çevirir
    
    currentEmotion = 5;   // Başlangıç ekranı: Uyuyor (Sleep)
    drawEyes();           // İlk arabellek ekrana basılıyor
    
    initI2S();            // TinyML mikrofon giriş katmanı sürücüsü kuruluyor
    initAMP();            // Python konuşma sentezi çıkış katmanı sürücüsü kuruluyor
    
    // Güvenli Servo Başlangıç Kalibrasyonu: Kafanın merkez açılarda kilitlenmesi
    panServo.attach(PAN_PIN);
    tiltServo.attach(TILT_PIN);
    panServo.write(90);
    tiltServo.write(120);
    
    sonHareketZamani = millis();
    motorlarAktif = true;
    sonAktiviteZamani = millis();
    Serial.println("[SİSTEM] Robi ESP32-S3 Başlatıldı. Dinamik Ses Protokolü Aktif.");
}

// =============================================================================
// 🔄 5. ANA YÜRÜTME DÖNGÜSÜ (LOOP)
// =============================================================================
void loop() {
    // --- 🛡️ AĞ BAĞLANTI GÜVENLİK DUVARI ---
    // Soket koptuğunda ana döngüyü (loop) dondurmadan (non-blocking) arka planda
    // belirli aralıklarla Python sunucusuna yeniden bağlanmayı dener.
    if (!client.connected()) {
        if (millis() - sonBaglantiDenemesi > baglantiAraligi) {
            Serial.println("[AĞ UYARISI] Bağlantı koptu. Tekrar deneniyor...");
            client.connect(host, port);
            sonBaglantiDenemesi = millis();
        }
    }
    else {
        // Python Dashboard tarafından TCP soket hattına bir komut metni bırakıldı mı kontrolü
        if (client.available() > 0) {
            String gelenVeri = client.readStringUntil('\n'); // Satır sonuna kadar paketi oku
            gelenVeri.trim();
            if (gelenVeri.length() > 0) {
                Serial.println("[Wi-Fi GELEN KOMUT]: " + gelenVeri);
                komutAyristir(gelenVeri); // Gelen veriyi parser motoruna gönder
                sonAktiviteZamani = millis(); // Aktivite zamanlayıcısını güncelle
            }
        }
    }

    // --- 🌟 ADIMSAL SERVO İNTERPOLASYON SÜRÜCÜSÜ ---
    // Matematiksel olarak hedef açı ile mevcut açı arasındaki mesafe kapatılır.
    // Loop her döndüğünde kademeli açı güncellenerek sarsıntı (jitter) tamamen yok edilir.
    if (motorlarAktif && (millis() - sonServoGuncelleme > servoGuncellemeAraligi)) {
        sonServoGuncelleme = millis();
        bool kafaHareketEtti = false;
        
        // Pan (Yatay) Ekseni Yumuşatma
        if (abs(targetPan - currentPan) > 0.5) {
            if (currentPan < targetPan) currentPan += servoAdimHizi;
            else currentPan -= servoAdimHizi;
            if (!panServo.attached()) panServo.attach(PAN_PIN);
            panServo.write((int)currentPan);
            kafaHareketEtti = true;
        }
        
        // Tilt (Dikey) Ekseni Yumuşatma
        if (abs(targetTilt - currentTilt) > 0.5) {
            if (currentTilt < targetTilt) currentTilt += servoAdimHizi;
            else currentTilt -= servoAdimHizi;
            if (!tiltServo.attached()) tiltServo.attach(TILT_PIN);
            tiltServo.write((int)currentTilt);
            kafaHareketEtti = true;
        }
        
        if (kafaHareketEtti) {
            sonHareketZamani = millis(); // Motorun fiziksel olarak iş yaptığını doğrula
        }
    }

    // --- 💤 DONANIMSAL KORUMA KİLİDİ (AUTO-DETACH) ---
    // Robot hedef açıya ulaşıp durduktan 2 saniye sonra servolara giden sinyal kesilir (detach).
    // Bu sayede motorların ömrü uzar, dişli zorlanmaları biter ve elektronik vızıltı önlenir.
    if (motorlarAktif && (millis() - sonHareketZamani > serbestBirakmaGecikmesi)) {
        panServo.detach();
        tiltServo.detach();
        motorlarAktif = false;
    }

    // Zaman Aşımı Rutini: Eğer 30 saniye boyunca robota hiçbir veri akışı olmazsa
    // enerji tasarrufu ve gerçekçilik adına sistem otomatik olarak Uyku (Sleep) moduna girer.
    if (currentEmotion != 5 && (millis() - sonAktiviteZamani > 30000)) {
        currentEmotion = 5;
        drawEyes();
    }

    // Animasyonlu yüz ifadelerinin (Düşünme, Uyku, Yağmurlu vb.) ekran tazeleme periyodu (300ms)
    if (currentEmotion == 3 || currentEmotion == 5 || currentEmotion == 9 || currentEmotion == 10) {
        if (millis() - sonAnimasyonZamani > 300) {
            drawEyes();
            sonAnimasyonZamani = millis();
        }
    }

    // --- ✨ CANLI IDLE (BOŞTA KALMA) MOTORU ÇALIŞTIRICISI ---
    // Robot sadece NORMAL (0) moddayken ve son etkileşimin üzerinden 1.5 saniye geçtiyse
    // insansı göz kaydırma ve kırpma hareketlerini devreye alır.
    if (currentEmotion == 0) {
        if (millis() - sonAktiviteZamani > 1500) {
            // Gözler merkezdeyse, rastgele belirlenen (4-7 sn) süre sonunda yeni bir bakış yönü seçilir.
            if (idleState == 0 && (millis() - sonIdleZamani > random(4000, 7000))) {
                idleState = random(1, 6); // 1-5 arası rastgele durum seçimi
                sonIdleZamani = millis();

                if (idleState == 5) {
                    // Göz Kırpma Durumu (Anlık basık oval hat çizilir, 150ms sürer)
                    idleGozKirp = true;
                    idleDurumBitisZamani = millis() + 150;
                } else {
                    // Sağa, sola, aşağı, yukarı bakış durumları (800ms - 1500ms arası sürer)
                    idleGozKirp = false;
                    idleDurumBitisZamani = millis() + random(800, 1500);

                    if (idleState == 1)      { idleXOffset = -6; idleYOffset = 0; }  // Göz bebekleri sola kayar
                    else if (idleState == 2) { idleXOffset = 6;  idleYOffset = 0; }  // Göz bebekleri sağa kayar
                    else if (idleState == 3) { idleXOffset = 0;  idleYOffset = -4; } // Göz bebekleri yukarı kayar
                    else if (idleState == 4) { idleXOffset = 0;  idleYOffset = 4; }  // Göz bebekleri aşağı kayar
                }
                drawEyes(); // Üretilen pikselleri ekrana yansıt
            }
            // Aktif bakış süresi dolduğunda göz bebeklerini pürüzsüzce merkeze (0,0) çeken sıfırlama bloku
            else if (idleState != 0 && millis() > idleDurumBitisZamani) {
                idleState = 0;
                idleXOffset = 0;
                idleYOffset = 0;
                idleGozKirp = false;
                sonIdleZamani = millis();
                drawEyes(); 
            }
        }
    } else {
        // Eğer kullanıcı robota başka bir duygu (Kızgın, Üzgün vb.) gönderdiyse idle motoru güvenle kapatılır.
        if (idleState != 0 || idleGozKirp) {
            idleState = 0; idleXOffset = 0; idleYOffset = 0; idleGozKirp = false;
        }
    }

    // --- 🎙️ TINYML EDGE AI UYANMA KELİMESİ ANALİZ ÇEKİRDEĞİ ---
    arkaPlanMikrofonOku(); // Sürekli olarak arka plandaki I2S DMA tamponu dinlenir.
    
    // Arduino IDE Seri Çizici (Serial Plotter) için ses dalgalarının simüle edilerek basılması.
    static unsigned long sonPlotZamani = 0;
    if (millis() - sonPlotZamani > 100) {
        Serial.print("Ses_Sinyali:");
        Serial.println(inference_buffer[0]);
        sonPlotZamani = millis();
    }

    // Edge Impulse sinir ağı çalıştırılmak üzere sinyal sarmalına bağlanıyor
    signal_t signal;
    signal.total_length = EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE;
    signal.get_data = &mikrofonVerisiSagla;
    ei_impulse_result_t result = { 0 };
    
    // Yapay zeka modeli uçta (offline) koşturuluyor
    EI_IMPULSE_ERROR r = run_classifier(&signal, &result, false);
    if (r == EI_IMPULSE_OK) {
        // Her 1.5 saniyede bir yapay zeka çıkarım skorlarını konsola basan debug mekanizması
        static unsigned long debugZamani = 0;
        if (millis() - debugZamani > 1500) {
            Serial.print("[YAPAY ZEKA ANALİZİ] -> ");
            for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
                Serial.print(result.classification[ix].label);
                Serial.print(": ");
                Serial.print(result.classification[ix].value);
                Serial.print(" | ");
            }
            Serial.println();
            debugZamani = millis();
        }

        // Model çıktısında eğitilen "HeyRobi" kelimesinin olasılık skoru kontrol edilir
        for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
            if (strcmp(result.classification[ix].label, "HeyRobi") == 0 && result.classification[ix].value > 0.50) {
                Serial.print("\n🎯 [WAKE WORD DETECTED] Skor: ");
                Serial.println(result.classification[ix].value);
                
                // Python Dashboard'a "Kullanıcı uyanma kelimesini söyledi, mikrofonu aç" emri gönderilir
                if (client.connected()) client.println("WAKE");
                
                currentEmotion = 4; // SMILE (Mutlu Yüz)
                drawEyes();
                
                if (!motorlarAktif) { panServo.attach(PAN_PIN); tiltServo.attach(TILT_PIN); motorlarAktif = true; }

                // Kafayı anında sesin geldiği merkeze doğrultur (90, 120)
                targetPan = 90;
                targetTilt = 120;

                sonHareketZamani = millis();
                sonAktiviteZamani = millis();
                delay(1500); // Algılama sonrası geçici donma maskelemesi
                ilkDolumYapildi = false;
                currentEmotion = 3; // THINK (Düşünme/Yükleme modu)
                drawEyes();
            }
        }
    }
}

// =============================================================================
// 🎛️ 6. YARDIMCI GÖMÜLÜ FONKSİYONLAR VE SES SÜRÜCÜLERİ
// =============================================================================
void wifiBaglan() {
    /* Kablosuz ağ modem el sıkışma fonksiyonu */
    Serial.print("[Wi-Fi] Ağa Bağlanılıyor: ");
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\n[Wi-Fi BAŞARILI]");
}

void initI2S() {
    /* INMP441 Dijital Mikrofon Sürücü Altyapısı */
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX), // Master alıcı modunda
        .sample_rate = 16000,                               // TinyML için 16kHz standart frekans
        .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,       // Sensörün donanımsal çözünürlüğü
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,        // Mono ses kanalı
        .communication_format = (i2s_comm_format_t)(I2S_COMM_FORMAT_I2S),
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,           // 1. seviye donanımsal kesme
        .dma_buf_count = 8,                                 // Veri kaçırmamak için 8 adet DMA tamponu
        .dma_buf_len = 1024,
        .use_apll = false
    };
    i2s_pin_config_t pin_config = {
        .bck_io_num = I2S_SCK, .ws_io_num = I2S_WS, .data_out_num = I2S_PIN_NO_CHANGE, .data_in_num = I2S_SD
    };
    i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
    i2s_set_pin(I2S_PORT, &pin_config);
}

void initAMP() {
    /* MAX98357A I2S DAC Amplifikatör Sürücü Altyapısı */
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX), // Master verici modunda
        .sample_rate = 16000,                               // Python TTS Ahmet Sesi standart hızı
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,       // Akıcı diksiyon için 16-bit derinlik
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = (i2s_comm_format_t)(I2S_COMM_FORMAT_I2S),
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = 1024,
        .use_apll = false
    };
    i2s_pin_config_t pin_config = {
        .bck_io_num = AMP_SCK, .ws_io_num = AMP_WS, .data_out_num = AMP_SD, .data_in_num = I2S_PIN_NO_CHANGE
    };
    i2s_driver_install(AMP_PORT, &i2s_config, 0, NULL);
    i2s_set_pin(AMP_PORT, &pin_config);
}

void arkaPlanMikrofonOku() {
    /* 🎙️ Sliding Window (Kayan Pencere) Tabanlı TinyML Tampon Doldurma Rutini */
    size_t bytes_read;
    int buffer_index = 0;
    
    // Yapay zeka penceresi ilk açılışta tamamen boşken doldurulan blok
    if (!ilkDolumYapildi) {
        while (buffer_index < EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE) {
            size_t bytes_to_read = (EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE - buffer_index) * 4;
            if (bytes_to_read > sizeof(i2s_raw_buffer)) bytes_to_read = sizeof(i2s_raw_buffer);
            i2s_read(I2S_PORT, &i2s_raw_buffer, bytes_to_read, &bytes_read, portMAX_DELAY);
            int samples_read = bytes_read / 4;
            for (int i = 0; i < samples_read; i++) {
                dc_running_avg = (dc_running_avg * 511 + i2s_raw_buffer[i]) / 512; // DC Offset Temizliği
                int32_t pure_ac = i2s_raw_buffer[i] - dc_running_avg;
                inference_buffer[buffer_index++] = pure_ac >> 16; // 32-bit'ten 16-bit PCM formatına indirgeme
            }
        }
        ilkDolumYapildi = true;
    }
    // İlk dolum bittikten sonra verileri sürekli sola kaydırarak güncel sesleri alan optimize algoritma
    else {
        for (int i = 0; i < KAYDIRILACAK_ORNEK_SAYISI; i++) {
            inference_buffer[i] = inference_buffer[i + YENI_ORNEK_SAYISI];
        }
        buffer_index = KAYDIRILACAK_ORNEK_SAYISI;
        while (buffer_index < EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE) {
            size_t bytes_to_read = (EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE - buffer_index) * 4;
            if (bytes_to_read > sizeof(i2s_raw_buffer)) bytes_to_read = sizeof(i2s_raw_buffer);
            i2s_read(I2S_PORT, &i2s_raw_buffer, bytes_to_read, &bytes_read, portMAX_DELAY);
            int samples_read = bytes_read / 4;
            for (int i = 0; i < samples_read; i++) {
                dc_running_avg = (dc_running_avg * 511 + i2s_raw_buffer[i]) / 512;
                int32_t pure_ac = i2s_raw_buffer[i] - dc_running_avg;
                inference_buffer[buffer_index++] = pure_ac >> 16;
            }
        }
    }
}

int mikrofonVerisiSagla(size_t offset, size_t length, float *out_ptr) {
    // Edge Impulse kütüphanesinin dahili DSP işlemcisine int16 verileri float olarak teslim eden köprü
    numpy::int16_to_float(&inference_buffer[offset], out_ptr, length);
    return 0;
}

void komutAyristir(String veri) {
    /* 📑 PYTHON'DAN GELEN Wi-Fi EMİR PAKETLERİNİ ÇÖZEN AYRIŞTIRICI (PARSER) */
    if (veri.startsWith("E:")) {
        // OLED Duygu Durum Değişikliği Paketi
        String ifade = veri.substring(2); ifade.trim();
        if (ifade == "NORMAL") currentEmotion = 0;
        else if (ifade == "SAD") currentEmotion = 1;
        else if (ifade == "ANGRY") currentEmotion = 2;
        else if (ifade == "THINK") currentEmotion = 3;
        else if (ifade == "SMILE") currentEmotion = 4;
        else if (ifade == "SLEEP") currentEmotion = 5;
        else if (ifade == "FOCUS") currentEmotion = 6;
        else if (ifade == "WINK") currentEmotion = 7;
        else if (ifade == "SUNNY") currentEmotion = 8;
        else if (ifade == "RAINY") currentEmotion = 9;
        else if (ifade == "SNOWY") currentEmotion = 10;
        drawEyes();
    }
    else if (veri.startsWith("P:")) {
        // Pan (Yatay Eksen) Açı Emir Paketi
        int aci = veri.substring(2).toInt();
        // Geliştirilmiş Mekanik Güvenlik Duvarı: Pan açısı donanım zorlanmasını önlemek için 60-120 dereceye kısıtlanmıştır
        targetPan = constrain(aci, 60, 120); 
        if (!motorlarAktif) { panServo.attach(PAN_PIN); tiltServo.attach(TILT_PIN); motorlarAktif = true; }
        sonHareketZamani = millis();
    }
    else if (veri.startsWith("T:")) {
        // Tilt (Dikey Eksen) Açı Emir Paketi
        int aci = veri.substring(2).toInt();
        // Geliştirilmiş Mekanik Güvenlik Duvarı: Fiziksel boyun tasarımı gereği dikey servo açısı 95-140 derece ile sınırlandırılmıştır
        targetTilt = constrain(aci, 95, 140); 
        if (!motorlarAktif) { panServo.attach(PAN_PIN); tiltServo.attach(TILT_PIN); motorlarAktif = true; }
        sonHareketZamani = millis();
    }
    else if (veri.startsWith("AUDIO:")) {
        // --- 🔉 CANLI SES PROSESÖRÜ VE SES AKIŞ ÇÖZÜCÜ ---
        int ilkIkiNokta = veri.indexOf(':', 6);
        int ikinciIkiNokta = veri.indexOf(':', ilkIkiNokta + 1);

        int sesBoyutu = veri.substring(6, ilkIkiNokta).toInt();
        int frekans = veri.substring(ilkIkiNokta + 1, ikinciIkiNokta).toInt();
        int kanallar = veri.substring(ikinciIkiNokta + 1).toInt();

        Serial.printf("[SİSTEM] Dinamik Kalibrasyon -> Frekans: %d Hz, Kanal: %d, Boyut: %d bayt\n", frekans, kanallar, sesBoyutu);

        // I2S donanım saat hızı gelen sesin kalitesine göre anlık dinamik olarak yeniden yapılandırılır
        i2s_channel_t i2s_ch = (kanallar == 2) ? I2S_CHANNEL_STEREO : I2S_CHANNEL_MONO;
        i2s_set_clk(AMP_PORT, frekans, I2S_BITS_PER_SAMPLE_16BIT, i2s_ch);
        
        currentEmotion = 4; // Konuşurken mutlu yüz ifadesini takın
        drawEyes();
        
        int okunanToplam = 0;
        uint8_t sesBuffer[512];
        
        // Gelen tüm ses paketleri tamamen bitene kadar ağ tamponundan okunup hoparlöre basılır
        while (okunanToplam < sesBoyutu && client.connected()) {
            if (client.available() > 0) {
                int okunabilir = min(sizeof(sesBuffer), (size_t)(sesBoyutu - okunanToplam));
                int n = client.read(sesBuffer, okunabilir);

                if (n > 0) {
                    size_t bytes_written;
                    // Ham 16-bit PCM veriler doğrudan I2S DMA tamponu üzerinden DAC amplifikatörüne basılır
                    i2s_write(AMP_PORT, sesBuffer, n, &bytes_written, portMAX_DELAY);
                    okunanToplam += n;
                }
            }
            
            // 🌟 ÇOKLU THREAD OPTİMİZASYONU ENJEKSİYONU: Robot konuşurken (yani bu yoğun while döngüsü içindeyken)
            // kafasının eş zamanlı olarak donmadan milim milim akıcı dönmesini sağlayan ara kontrol mekanizması.
            if (motorlarAktif && (millis() - sonServoGuncelleme > servoGuncellemeAraligi)) {
                sonServoGuncelleme = millis();
                if (abs(targetPan - currentPan) > 0.5) {
                    if (currentPan < targetPan) currentPan += servoAdimHizi; else currentPan -= servoAdimHizi;
                    if (!panServo.attached()) panServo.attach(PAN_PIN); panServo.write((int)currentPan);
                }
                if (abs(targetTilt - currentTilt) > 0.5) {
                    if (currentTilt < targetTilt) currentTilt += servoAdimHizi; else currentTilt -= servoAdimHizi;
                    if (!tiltServo.attached()) tiltServo.attach(TILT_PIN); tiltServo.write((int)currentTilt);
                }
            }
            yield(); // Donanımsal Watchdog (WDT) reset atmasını önleyen işlemci rahatlatma komutu
        }

        Serial.println("[SİSTEM] Robi konuşmayı tamamladı.");
        currentEmotion = 0; // Konuşma bitince normal gözlem moduna geri dön
        drawEyes();
    }
}

void drawEyes() {
    /* 🎨 U8G2 GRAFİK MOTORU VE GEOMETRİK OLED DUYGU ÇİZİMLERİ */
    u8g2.clearBuffer(); // Ekran arabelleğini RAM üzerinde temizle
    u8g2.setDrawColor(1);
    
    // Göz yapısının temel geometrik standart ölçüleri
    int baseWidth = 46; int baseHeight = 52; int cornerRadius = 8;
    int eye1X = 34 - (baseWidth / 2); int eye2X = 94 - (baseWidth / 2); int eyeY = 32 - (baseHeight / 2);
    
    if (currentEmotion == 0) { // --- NORMAL MOD ---
        if (idleGozKirp) {
            int blinkHeight = 8; int blinkY = 32 - (blinkHeight / 2) + 4;
            u8g2.drawRBox(eye1X, blinkY, baseWidth, blinkHeight, 4);
            u8g2.drawRBox(eye2X, blinkY, baseWidth, blinkHeight, 4);
        } else {
            // Göz pikselleri boşta kalma motorundan gelen ofset miktarına göre organik olarak kaydırılır
            u8g2.drawRBox(eye1X + idleXOffset, eyeY + idleYOffset, baseWidth, baseHeight, cornerRadius);
            u8g2.drawRBox(eye2X + idleXOffset, eyeY + idleYOffset, baseWidth, baseHeight, cornerRadius);
        }
    }
    else if (currentEmotion == 1) { // --- ÜZGÜN (SAD) MOD ---
        u8g2.drawRBox(eye1X, eyeY, baseWidth, baseHeight, cornerRadius);
        u8g2.drawRBox(eye2X, eyeY, baseWidth, baseHeight, cornerRadius);
        u8g2.setDrawColor(0); // Kaşları bükmek için siyah renkli ters maskeleme üçgenleri çiziliyor
        u8g2.drawTriangle(eye1X - 2, eyeY - 2,  eye1X + 30, eyeY - 2,  eye1X - 2, eyeY + 24);
        u8g2.drawTriangle(eye2X + baseWidth + 2, eyeY - 2,  eye2X + baseWidth - 30, eyeY - 2,  eye2X + baseWidth + 2, eyeY + 24);
    }
    else if (currentEmotion == 2) { // --- KIZGIN (ANGRY) MOD ---
        u8g2.drawRBox(eye1X, eyeY, baseWidth, baseHeight, cornerRadius);
        u8g2.drawRBox(eye2X, eyeY, baseWidth, baseHeight, cornerRadius);
        u8g2.setDrawColor(0); // Sert bakış maskeleme üçgenleri
        u8g2.drawTriangle(eye1X + baseWidth + 2, eyeY - 2,  eye1X + baseWidth - 30, eyeY - 2,  eye1X + baseWidth + 2, eyeY + 24);
        u8g2.drawTriangle(eye2X - 2, eyeY - 2,  eye2X + 30, eyeY - 2,  eye2X - 2, eyeY + 24);
    }
    else if (currentEmotion == 3) { // --- DÜŞÜNÜYOR (THINK) MODU ---
        int thinkWidth = 36; int eye1X_think = 34 - (thinkWidth / 2); int eye2X_think = 94 - (thinkWidth / 2);
        u8g2.drawRBox(eye1X_think, eyeY - 10, thinkWidth, baseHeight, cornerRadius);
        u8g2.drawRBox(eye2X_think, eyeY - 10, thinkWidth, baseHeight, cornerRadius);
        u8g2.setDrawColor(0); u8g2.drawBox(0, 32, 128, 32); u8g2.setDrawColor(1);
        int dotsX = 118; int step = (millis() / 300) % 4; // Noktaların yükselme animasyonu
        if (step >= 1) u8g2.drawDisc(dotsX, 46, 2);
        if (step >= 2) u8g2.drawDisc(dotsX, 34, 3);
        if (step >= 3) u8g2.drawDisc(dotsX, 20, 4);
    }
    else if (currentEmotion == 4) { // --- MUTLU (SMILE) MOD ---
        int happyHeight = 38; int happyY = 32 - (happyHeight / 2);
        u8g2.drawRBox(eye1X, happyY, baseWidth, happyHeight, 10);
        u8g2.drawRBox(eye2X, happyY, baseWidth, happyHeight, 10);
        u8g2.setDrawColor(0); u8g2.drawBox(0, 32, 128, 32); // Kısık göz efekti için alt yarıyı kapat
    }
    else if (currentEmotion == 5) { // --- UYKU (SLEEP) MODU ---
        int sleepHeight = 8; int sleepY = 32 - (sleepHeight / 2) + 12;
        u8g2.drawRBox(eye1X, sleepY, baseWidth, sleepHeight, 4);
        u8g2.drawRBox(eye2X, sleepY, baseWidth, sleepHeight, 4);
        u8g2.setFont(u8g2_font_6x10_tf);
        int step = (millis() / 400) % 4; // Ekrana periyodik Zzz basan algoritma
        if (step == 1)      u8g2.drawStr(102, 16, "z");
        else if (step == 2) u8g2.drawStr(102, 16, "zz");
        else if (step == 3) u8g2.drawStr(102, 16, "Zzz");
    }
    else if (currentEmotion == 6) { // --- ODAK (FOCUS) MODU ---
        int focusHeight = 18; int focusY = 32 - (focusHeight / 2);
        u8g2.drawRBox(eye1X, focusY, baseWidth, focusHeight, 6);
        u8g2.drawRBox(eye2X, focusY, baseWidth, focusHeight, 6);
    }
    else if (currentEmotion == 7) { // --- GÖZ KIRPMA (WINK) MODU ---
        u8g2.drawRBox(eye1X, eyeY, baseWidth, baseHeight, cornerRadius);
        int winkHeight = 8; int winkY = 32 - (winkHeight / 2) + 12;
        u8g2.drawRBox(eye2X, winkY, baseWidth, winkHeight, 4);
    }
    else if (currentEmotion == 8) { // --- GÜNEŞLİ (SUNNY) MOD ---
        u8g2.drawDisc(64, 32, 14);
        for (int i = 0; i < 360; i += 45) { // Trigonometrik güneş ışınları çizimi
            float rad = i * DEG_TO_RAD;
            int x1 = 64 + cos(rad) * 18;  int y1 = 32 + sin(rad) * 18;
            int x2 = 64 + cos(rad) * 24;  int y2 = 32 + sin(rad) * 24;
            u8g2.drawLine(x1, y1, x2, y2);
        }
    }
    else if (currentEmotion == 9) { // --- YAĞMURLU (RAINY) MOD ---
        u8g2.drawDisc(54, 26, 10); u8g2.drawDisc(68, 22, 14); u8g2.drawDisc(80, 26, 9);
        u8g2.drawBox(52, 26, 30, 10); // Bulut geometrik birleşimi
        int toggle = (millis() / 150) % 2; // Yağmur damlalarının akma animasyonu
        if (toggle == 0) {
            u8g2.drawLine(54, 42, 51, 49); u8g2.drawLine(68, 42, 65, 49); u8g2.drawLine(80, 42, 77, 49);
        } else {
            u8g2.drawLine(51, 45, 48, 52); u8g2.drawLine(65, 45, 62, 52); u8g2.drawLine(77, 45, 74, 52);
        }
    }
    else if (currentEmotion == 10) { // --- KARLI (SNOWY) MOD ---
        u8g2.drawDisc(54, 26, 10); u8g2.drawDisc(68, 22, 14); u8g2.drawDisc(80, 26, 9);
        u8g2.drawBox(52, 26, 30, 10);
        int flash = (millis() / 300) % 2; // Kar tanesi piksellerinin yer değiştirmesi
        if (flash == 0) {
            u8g2.drawPixel(52, 44); u8g2.drawPixel(66, 48); u8g2.drawPixel(78, 43); u8g2.drawPixel(60, 53);
        } else {
            u8g2.drawPixel(54, 48); u8g2.drawPixel(68, 44); u8g2.drawPixel(80, 49); u8g2.drawPixel(72, 52);
        }
    }
    u8g2.sendBuffer(); // RAM'deki çizimleri fiziksel OLED panele aktar
}