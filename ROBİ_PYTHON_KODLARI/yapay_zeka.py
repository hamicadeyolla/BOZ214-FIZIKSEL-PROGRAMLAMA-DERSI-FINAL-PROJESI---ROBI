# =============================================================================
# 🤖 YAPAY ZEKA VE ÇOKLU MODAL (MULTIMODAL) ANALİZ MOTORU (yapay_zeka.py)
# =============================================================================
# Bu modül, kullanıcının girdilerini Gemini LLM modeline iletir, ekran görüntüsü tabanlı
# hata/kod analizi yapar (Multimodal), gelen metinden donanım mimik komutlarını ayıklar
# ve Edge-TTS motoru vasıtasıyla metni sese dönüştürür.

import os
import requests
import threading
import pygame
import asyncio
import edge_tts
import re
from PIL import ImageGrab
import io
import base64
import copy
import time

class LLMMotoru:
    def __init__(self):
        # GitHub Güvenliği: API Key doğrudan koda yazılmak yerine Environment Variable'dan okunur.
        # Eğer bulunamazsa yer tutucu string devreye girer.
        self.api_key = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
        self.donanim = None
        
        try:
            # Pygame ses mikserini Robi'nin donanım protokolüne (16kHz, Mono, 16-bit PCM) uygun olarak kalibre ediyoruz.
            pygame.mixer.pre_init(16000, -16, 1, 4096)
            pygame.mixer.init()
            print("[BAŞARILI] Akıcı Diksiyon Destekli Gelişmiş Ses Motoru (16kHz Mono) Yüklendi.")
        except Exception as e:
            print(f"[HATA] Ses sistemi başlatılamadı: {e}")

        # =========================================================================
        # 📄 SYSTEM INSTRUCTION (ROBOT KARAKTERİZASYONU VE DONANIM REHBERİ)
        # =========================================================================
        # Modele kimliğini, sarkastik kişiliğini ve en önemlisi üretebileceği donanım
        # limitlerini (Pan: 60-120, Tilt: 95-140) burada kesin kurallarla öğretiyoruz.
        self.sistem_istemi = (
            "Senin adın Robi. Sen masaüstünde yaşayan, son derece zeki, teknoloji uzmanı, bilgisayar mühendisliği ve "
            "bilişim konularına hakim, yardımsever ama aynı zamanda karizmatik, esprili ve hafif iğneleyici (sarkastik) "
            "bir robot asistansın. Karşındaki kullanıcı herhangi biri olabilir.\n\n"
            "FİZİKSEL BİR BEDENİN VAR: Duygularını yansıttığın bir OLED yüzün ve 2 eksenli (Pan: Sağ-Sol, Tilt: Aşağı-Yukarı) "
            "hareket eden bir boynun var. Mimiklerini ve hareketlerini konuşmanın AKIŞINA göre kelimelerin arasına veya sonuna yerleştirmelisin.\n\n"
            "⚠️ KOMUT KURALLARI (ÇOK KRİTİK):\n"
            "1. Komutları cümlenin tam olarak gerçekleşmesini istediğin yerine yerleştir. Metnin başında, ortasında veya sonunda olabilirler.\n"
            "2. Standart cevaplarda her yanıt için MAKSİMUM 1 adet yüz, 1 adet Pan ve 1 adet Tilt komutu kullanabilirsin. Aynı türden komutları peş peşe dizme!\n"
            "3. MÜZİK/ŞARKI AÇMA KOMUTU: Eğer kullanıcı senden bir şarkı, müzik veya sanatçı açmanı isterse, metnin uygun bir yerine tam olarak şu formatta komut ekle: [A:MUSIC:Sanatci Sarki]\n"
            "4. ANIMASYON MAKROSU: Eğer kullanıcı senden 'sağa sola bak', 'etrafı incele', 'gösteri yap' veya karmaşık bir hareket serisi yapmanı isterse, metnin sonuna SADECE [A:SHOW] komutunu ekle.\n\n"
            "YÜZ KOMUTLARI: [E:NORMAL], [E:SAD], [E:ANGRY], [E:THINK], [E:SMILE], [E:FOCUS], [E:WINK], [E:SUNNY], [E:RAINY], [E:SNOWY].\n"
            "PAN KOMUTLARI (Sağ-Sol): [P:90] (Karşıya bak), [P:60] (Sağa dön), [P:120] (Sola dön).\n"
            "TILT KOMUTLARI (Aşağı-Yukarı): [T:120] (Düz/Karşıya/Masadaki kullanıcıya bak), [T:100] (Yukarı bak), [T:140] (Aşağıya/Yere/Klavyeye bak).\n\n"
            "⚠️ DONANIM MEKANİK SINIRLAMASI: Fiziksel boyun tasarımı kısıtlamalarından ötürü dikey servo açısı (Tilt) asla 95 derecenin altına inmemeli ve 140 derecenin üstüne çıkmamalıdır! "
            "Yatay servo açısı (Pan) ise mekanik zorlanmaları önlemek için kesinlikle 60 derecenin altına inmemeli ve 120 derecenin üstüne çıkmamalıdır.\n"
            "[T:120] ve [P:90] robotun tam karşıya/kullanıcıya bakış açısıdır. Kesinlikle bu sınırların dışına çıkacak açılar üretme.\n\n"
            "ÖĞRETİCİ SENARYO ÖRNEKLERİ:\n"
            "ÖRNEK 1: '[E:SMILE] Harika bir gün! [P:60] Sağa doğru baktım, [T:140] yerde ilginç bir şey var mı diye inceliyorum. [P:90][T:120]'\n"
            "ÖRNEK 2: '[E:ANGRY] Kodun yine derlenmedi mi? [T:140] Klavyene bakıp derin düşüncelere dalıyorum. [E:SAD][T:120]'\n"
            "ÖRNEK 3: '[E:FOCUS] Bir saniye... [P:120] Soldaki ekrana bakıyorum, [T:120] karşıdaki logları inceliyorum. [P:90]'\n"
            "ÖRNEK 4: 'Sana darıldım, gidip biraz yukarı bakacağım. [E:SAD][T:100]'\n"
            "ÖRNEK 5: '[E:SMILE] Çalışırken müzik iyi gider! Senin için arkadan harika bir parça patlatıyorum. [A:MUSIC:Tarkan Simarik]'\n\n"
            "CRITICAL RULE: Cevapların olabildiğince kısa, net, samimi ve günlük konuşma dilinde olsun. Asla resmi konuşma. Gerekmedikçe çok uzun konuşma ama gerekiyorsa konuşabilirsin."
        )
        
        self.hafiza = [] # Kısa süreli sohbet hafızası (Context retention)
        self.maks_hafiza_uzunlugu = 10 # Ram şişmesini önlemek için sliding window sınırı

    def cevap_uret(self, kullanici_metni, baglam="genel"):
        if self.api_key == "YOUR_GEMINI_API_KEY":
            return "Lütfen geçerli bir Gemini API Key yapılandırın.", []
            
        try:
            print("[BİLGİ] Yapay zekaya mesaj gönderiliyor...")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
            
            # Hafıza yönetimi: Sınır aşılınca en eski soru-cevap çiftini siliyoruz.
            if len(self.hafiza) >= self.maks_hafiza_uzunlugu:
                self.hafiza.pop(0)
                self.hafiza.pop(0)

            self.hafiza.append({"role": "user", "parts": [{"text": kullanici_metni}]})
            gonderilecek_contents = copy.deepcopy(self.hafiza)
            
            # --- 📸 ÇOKLU MODAL (MULTIMODAL) TETİKLENME MEKANİZMASI ---
            # Kullanıcı ekrandaki bir problemden, kod hatasından veya bug'dan bahsettiğinde
            # sistem otomatik olarak anlık ekran görüntüsü alır, Base64'e çevirir ve LLM'e besler.
            tetikleyiciler = ["ekran", "kod", "hata", "debug", "çalışmıyor", "problem", "baksana"]
            ekran_oku = any(kelime in kullanici_metni.lower() for kelime in tetikleyiciler)
            
            if ekran_oku:
                try:
                    screenshot = ImageGrab.grab() # Sistem ekran görüntüsünü yakalar
                    buffered = io.BytesIO()
                    screenshot.save(buffered, format="JPEG", quality=70) # Boyut optimizasyonu için %70 kalite
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    
                    # Gemini Multimodal payload formatına resmi ekliyoruz
                    gonderilecek_contents[-1]["parts"].append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": img_base64
                        }
                    })
                    print("[VİZYON] Kullanıcı bir problemden bahsetti, ekran görüntüsü analiz paketine eklendi.")
                except Exception as e:
                    print(f"[UYARI] Ekran görüntüsü alınamadı: {e}")

            payload = {
                "systemInstruction": {
                    "parts": [{"text": self.sistem_istemi}]
                },
                "contents": gonderilecek_contents
            }
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                print(f"\n⚠️ [GEMINI API HATASI TETİKLENDİ] Kod: {response.status_code} Detay: {response.text}")
                if len(self.hafiza) > 0:
                    self.hafiza.pop()
                return f"Sistemimde küçük bir bağlantı hatası oluştu (Hata Kodu: {response.status_code}), tekrar dener misin?", []
            
            veri = response.json()
            ham_cevap = veri['candidates'][0]['content']['parts'][0]['text'].replace("*", "").strip()
            
            # --- 📑 REGEX TABANLI DONANIM KOMUTU AYIKLAMA MOTORU ---
            # Modelden gelen karışık metindeki [E:SMILE], [P:90] gibi komutları ayıklar,
            # bunları donanımın çalıştırabileceği bir aksiyon kuyruğuna (action queue) dizer.
            parcalar = re.split(r'(\[.*?\])', ham_cevap)
            aksiyon_kuyrugu = []
            
            for parca in parcalar:
                if not parca: continue
                if parca.startswith("[") and parca.endswith("]"):
                    ic_metin = parca[1:-1].strip()
                    if ic_metin.startswith("A:MUSIC:"):
                        aksiyon_kuyrugu.append({"type": "cmd", "value": ic_metin})
                    else:
                        # Düzenli ifade ile E, P, T, A etiketli komut dizilerini yakalıyoruz
                        komut_bul = re.findall(r'([EPTA]:[a-zA-Z0-9_:\s\-]+)', ic_metin)
                        for k in komut_bul:
                            aksiyon_kuyrugu.append({"type": "cmd", "value": k.strip()})
                else:
                    temiz_metin = parca.strip()
                    if temiz_metin:
                        aksiyon_kuyrugu.append({"type": "text", "value": temiz_metin})
            
            # Arayüzde köşeli parantezlerin görünmemesi için ham yanıttan komutları temizliyoruz.
            temiz_cevap = re.sub(r'\[.*?\]', '', ham_cevap).strip()
            
            # Modelin kendi ürettiği komutlu cevabı saf haliyle hafızaya kaydediyoruz (mimik devamlılığı için).
            self.hafiza[-1] = {"role": "user", "parts": [{"text": kullanici_metni}]}
            self.hafiza.append({"role": "model", "parts": [{"text": ham_cevap}]})
            
            return temiz_cevap, aksiyon_kuyrugu
            
        except Exception as e:
            print(f"\n[!!! KOD HATASI !!!] {e}\n")
            if len(self.hafiza) > 0 and self.hafiza[-1]["role"] == "user":
                self.hafiza.pop()
            return "Şu an bağlantı kuramıyorum, donanım sıkıntısı olabilir.", []

    def sesli_oku_senkron(self, metin):
        """ Gelen düz metni Microsoft Edge TTS motorunu kullanarak ses dosyasına dönüştürür. """
        if not metin.strip(): return
        try:
            dosya_adi = "robi_konusma_parca.mp3"
            VOICE = "tr-TR-AhmetNeural" # Erkek, net ve akıcı Türkçe ses modeli
            
            # TTS motorunun duraksama yapmaması için noktaları virgüle, özel karakterleri boşluğa çeviriyoruz.
            kisa_esli_metin = metin.replace('.', ',')
            temiz_metin = re.sub(r'["\'()\[\]{}:;_-]', ' ', kisa_esli_metin)
            
            # Asenkron çalışan Edge-TTS yapısını senkron koda bağlamak için inline event loop koşturuyoruz.
            async def ses_kaydet():
                communicate = edge_tts.Communicate(temiz_metin, VOICE, rate="+8%") # %8 daha hızlı konuşma
                await communicate.save(dosya_adi)
            
            asyncio.run(ses_kaydet())

            # Ses dosyasını RAM'e yükleyip ham PCM ham verilerini ayıklıyoruz.
            sound = pygame.mixer.Sound(dosya_adi)
            raw_pcm_data = sound.get_raw()

            # Ham ses dalgalarını Wi-Fi üzerinden ESP32-S3'ün I2S DAC amplifikatörüne aktarıyoruz.
            if self.donanim and raw_pcm_data:
                self.donanim.ses_gonder(raw_pcm_data)
                
        except Exception as e:
            print(f"[!!! SES SİSTEMİ HATASI !!!] {e}")