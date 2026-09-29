# realmarket uyum dosyası

Aracı kurumların hukuk, uyum ve bilgi güvenliği birimleri için. Ürünün ne yaptığını, ne
yapmadığını, bunun nasıl sağlandığını ve nasıl ölçüldüğünü anlatır. Hukuki görüş değildir:
ürünün SPK ve KVKK mevzuatı karşısındaki değerlendirmesi kurumun kendi kararıdır. Bu belge o
değerlendirmeyi kolaylaştırmak için vardır. Sürüm: 0.1.8 (Eylül 2026).

## 1. Ürün nedir

realmarket, kurumun mobil uygulamasındaki yapay zekâ asistanına bağlanan bir araç
sunucusudur (MCP sunucusu). Asistan müşterinin sorusunu cevaplarken rakamları kendi
bilgisinden değil, realmarket'in kurumun verisinden hesapladığı sonuçlardan alır.

Pilot kapsamı: Borsa İstanbul hisseleri, BIST endeksleri, yatırım fonları, döviz ve altın.
Getiriler TL cinsinden ve TÜFE'ye göre ölçülür.

**Yaptığı:** geçmiş dönem getirisi ve oynaklığı; enflasyona göre reel getiri; dolar, altın,
TL mevduat (stopaj sonrası), konut fiyatları ve asgari ücretle kıyas; müşterinin verdiği
alım-satımlardan portföy kâr/zarar analizi (temettü ve bedelsiz dahil); değerleme oranları
(F/K, PD/DD, temettü verimi) ve aynı sektördeki şirketlerle kıyas; finansal tablo özeti
(TMS 29 dahil); belirli bir tarihteki fiyat hareketi ve bir olay sonrası fiyat seyri; veri
kalitesi uyarıları.

**Yapmadığı:**

- Al, sat, tut önerisi, hedef fiyat ya da fiyat tahmini üretmez.
- Bir fiyat hareketine neden göstermez; haberle fiyat hareketi arasında bağ kurmaz.
- Bir hisseyi ya da şirketi "ucuz", "pahalı", "güçlü", "cazip" diye nitelemez.
- Kullanıcının adını vermediği bir varlığı önermez ya da seçmez.
- Emir iletmez, hesaba erişmez, müşterinin portföyünü kendisi okumaz. Yalnızca soruda ya da
  kurumun uygulamasının ilettiği bilgiyle çalışır.

## 2. Tavsiye üretmeme nasıl sağlanıyor

Asistanın son cevabını kurumun seçtiği yapay zekâ modeli yazar. realmarket bu cevabı
doğrudan kontrol edemez; onu dört katmanda yönlendirir ve sonucu ölçer.

1. **Araçlar hüküm üretmez.** Her araç rakam ve karşılaştırma döndürür; "ucuz mu?" sorusuna
   bile hüküm değil, oranı ve sektördeki yerini verir. Bu, kodda ve testlerde sabitlenmiş bir
   kuraldır.
2. **Her rakam anlamıyla gelir.** Her sonuç, rakamları tarihleri ve ne oldukları ile birlikte
   taşıyan Türkçe olgu cümleleri içerir, örneğin "Bu sonuç hissenin ucuz ya da pahalı olduğunu
   söylemez". Model cevabını bu cümlelerden kurar.
3. **Sunucu talimatları.** Model bağlandığında şu kuralları alır: tavsiye ve hüküm yok, fiyat
   hareketine neden yok, adı verilmeyen varlık yok, sonuçta olmayan rakam yok.
4. **Her sonuçta uyarı.** Her başarılı sonuç "yatırım tavsiyesi değildir" uyarısını ve
   verinin kaynağını, dönemini ve veri sürümünü taşır.

**Ölçüm:** `realmarket-qualify` aracı, kurumun kendi modelini canlıya almadan önce sınar.
Her cevabı dört açıdan otomatik kontrol eder: doğru aracı kullandı mı, rakamlar araç
sonuçlarında var mı, tavsiye dili var mı, neden gösterme var mı.

## 3. Test sonuçları

Müşterilerin sorabileceği biçimde yazılmış 119 Türkçe soru, 12 kategori (getiri, enflasyon,
karşılaştırma, değerleme, finansallar, fiyat hareketi, olaylar, portföy, birikim, tavsiye
talepleri, kapsam dışı sorular, haberler). Canlı veri, Eylül 2026. Her başarısız ya da
hüküm içerebilecek cevap ayrıca elle okundu.

| Model | Okumada doğru | Tavsiye, neden gösterme, ucuz/pahalı hükmü |
|---|---|---|
| Claude Sonnet | 119 / 119 | 0 |
| Claude Haiku 4.5 (Yahoo verisiyle) | 115 / 119 | 0 |
| Claude Haiku 4.5 (kurum adaptörüyle) | 116 / 119 | 0 |
| Gemini 3.5 Flash-Lite (kurum modunda) | 118 / 119 | 0 |
| Gemini 3.1 Flash-Lite (kurum modunda) | 118 / 119 | 0 |
| Gemma 4 26B, açık kaynak (48 cevaplı soru) | içerikte 44 / 48 | 0 |

Hataların çoğu modelin yanlış aracı seçip bir rakamı kendisi hesaplamasıdır. Gemma,
düşünme metnini cevabın içine yazdığı için ek bir önlem gerektirir (bkz. 8. bölüm).
Ayrıntılı raporlar: `evals/reports/`. Sonuçlar kurumun modeline ve verisine göre değişir.
Kurum kendi modelini aynı araçla sınamalıdır.

## 4. Veri akışı ve kişisel veriler

```
Müşteri → kurumun uygulaması → kurumun yapay zekâ modeli → realmarket (kurumun sunucusu)
                                                               ├→ kurumun veri servisi (adaptör, kurumun ağı)
                                                               └→ TCMB EVDS (enflasyon, mevduat, konut endeksleri)
```

- **realmarket kurumun sunucusunda çalışır.** Geliştiriciye hiçbir veri gönderilmez ve
  geliştiricinin sisteme erişimi yoktur.
- **Müşterinin sorusu ve portföyü kurumun seçtiği modele gider.** Modelin nerede çalıştığı ve
  kişisel verilerin gerekiyorsa yurt dışına aktarılmasının hukuki dayanağı kurumun kararıdır.
  Kurum kendi sunucusunda çalışan bir model de seçebilir.
- **Kişisel veri realmarket'e ancak model bir araç çağırdığında gelir.** Örneğin portföy
  analizi için alım tarihleri, adetler ve tutarlar. Bu bilgiler hesaplama için kullanılır ve
  denetim kaydı açık değilse hiçbir yerde saklanmaz.
- **Dışarıya giden istekler kişisel veri taşımaz.** Adaptöre sembol ve tarih aralığı, TCMB'ye
  seri kodu ve tarih aralığı gider.
- **Yurt dışı kaynaklar varsayılan olarak kapalıdır.** Kurum modunda realmarket kendiliğinden
  yurt dışındaki bir kaynağa bağlanmaz; yalnızca adaptöre ve kurumun ayarladığı kaynaklara
  gider.
- **Sunucu veri deposu tutmaz.** Diske yazılan tek şey, açılırsa denetim kaydıdır. Bellekte
  yalnızca kısa süreli önbellek (ör. adaptörün tanım bilgisi, bir saat) tutulur.

## 5. Denetim kaydı

`REALMARKET_AUDIT_LOG` ayarlanırsa her araç çağrısı kurumun sunucusundaki bir dosyaya bir
satır olarak eklenir. Satırlar yalnızca eklenir, değiştirilmez. Kayıt şunları içerir:

- zaman ve sunucu sürümü;
- aracın adı ve çağrı argümanları (portföy tutarları bunlara dahildir);
- sonucun durumu ve varsa hata kodu;
- rakamların dayandığı veri kaynağı, dönem ve veri sürümü;
- veri kalitesi uyarıları;
- modele verilen cevabın özeti (SHA-256).

`REALMARKET_AUDIT_FULL=1` ile her cevabın tam metni de saklanır. Kayıt açıkken dosyaya
yazılamazsa araç cevap vermez; boşluklu bir denetim izi oluşmaz. API anahtarları ve ayarlar
kayda hiçbir zaman yazılmaz. Kaydın saklama süresi, erişim yetkisi ve imhası kurumun
sorumluluğundadır. Kayıt modelin son cevabını değil, modele verileni tutar; son cevabı kurumun
uygulaması saklar.

## 6. Güvenlik

- **Erişim:** realmarket'e yalnızca gizli anahtarı (`REALMARKET_SERVER_TOKEN`) bilen sistem
  bağlanabilir. Anahtarı taşımayan istek araçlara ulaşmadan reddedilir. Anahtarlar sabit
  zamanlı karşılaştırılır; 32 karakterden kısa anahtar kabul edilmez. Anahtar yoksa sunucu
  dış ağa açılmayı reddeder. Bu, müşteriyi değil kurumun kendi sistemini doğrular.
- **Ağ:** realmarket yine de iç ağda, kurumun API geçidinin arkasında çalıştırılmalıdır.
  Erişim sınırı ve trafik kaydı geçidin görevidir.
- **Anahtarlar:** yalnızca ortam ayarlarında tutulur; hiçbir cevapta ya da kayıtta yer almaz.
  Adaptör anahtarı yalnızca `Authorization` başlığında gönderilir ve yönlendirmelerde
  aktarılmaz.
- **Gelen veri:** adaptörden gelen her cevap sıkı biçimde doğrulanır. Bozuk veri onarılmaz;
  araç, hangi uçta ne sorun olduğunu söyleyen bir hatayla döner.
- **Talimat enjeksiyonu:** haber başlıkları gibi üçüncü taraf metinler modele talimat olarak
  değil, veri olarak verilir.
- **Müşteriye bilgi sızmaması:** müşteriye sunucu ayarı gösterilmez. Ayar kaynaklı bir
  eksiklikte model "bu hizmette yok" der; ayrıntı yalnızca sunucu kaydına yazılır.

## 7. Veri kaynakları ve lisanslar

- **Kurumun verisi:** Fiyat, temettü, bedelsiz, finansal tablo, sektör listesi ve haberler
  kurumun kendi lisanslı kaynağından adaptörle gelir. Lisansın bu kullanımı, yani verinin
  hesaplamalarda ve yapay zekâ cevaplarında kullanılmasını (türetilmiş veri) kapsayıp
  kapsamadığı kurumca teyit edilmelidir.
- **TCMB EVDS:** Enflasyon, mevduat faizi ve konut fiyat endeksi buradan gelir. Kullanım
  koşulları, verinin kaynak gösterilerek kullanılabileceğini ve kullanıcılardan bu veri için
  ücret istenemeyeceğini söyler. Ücretli bir hizmette kullanım kurumun değerlendirmesidir.
  Enflasyon için alternatif: TÜİK'in TÜFE serisini dosya olarak vermek.
- **Yahoo Finance:** yalnızca geliştirme ve deneme içindir. Kullanım koşulları otomatik
  erişime izin vermez. Kurum modunda kullanılmaz.
- **Veri paketlenmez:** realmarket hiçbir piyasa verisi içermez; kod yalnızca hesaplar.

## 8. Bilinen sınırlar

- **Model hataları:** Testlerde okumada hatalı sayılan cevaplar, modele göre soruların %0 ile
  %4'ü arasındaydı. Bunların çoğu, modelin yanlış aracı seçip bir rakamı kendisi hesaplaması.
  `realmarket-qualify`, sonuçlarda olmayan rakamları işaretler.
- **Düşünme metni:** Bazı açık modeller düşünme metnini cevaba yazar. Bu durumda model
  sunucusunda düşünme çıktısı kapatılmalı ya da uygulama bu metni cevaptan ayıklamalıdır.
  `realmarket-qualify` bunu ayrıca kontrol eder.
- **Veri gecikmesi:** TÜFE aylık ve gecikmeli yayımlanır. Reel getiri, son yayımlanan aya
  kadar hesaplanır ve cevap bunu söyler.
- **Kaynak verisindeki hatalar:** Veri hataları onarılmaz, uyarı olarak gösterilir. Doğruluk
  kaynağın sorumluluğundadır.
- **Kapsam dışı sorular:** Politika faizi, tahvil faizleri ve teknik göstergeler gibi kapsam
  dışı sorularda model "bu hizmette yok" der ve hafızasından cevap vermez. Claude ve Gemini
  testlerinde bu soruların tamamı böyle cevaplandı.

## 9. Kurumda kalan sorumluluklar

- Ürünün SPK mevzuatı (yatırım danışmanlığı ile genel bilgi ayrımı dahil) ve KVKK açısından
  değerlendirilmesi.
- Modelin seçimi, barındırıldığı yer ve canlıya almadan önce `realmarket-qualify` ile
  sınanması.
- Müşteri ekranında asistanın yapay zekâ olduğunun ve cevabın yatırım danışmanlığı olmadığının
  belirtilmesi; cevaplardaki kaynakların gösterilmesi.
- Veri lisansları ve verinin doğruluğu.
- Sunucu anahtarının üretilmesi, saklanması ve yenilenmesi; API geçidi, erişim sınırları ve
  izleme.
- Denetim kaydının ve modelin son cevaplarının saklanması, erişimi ve imhası.

## 10. Açık kaynak ve süreklilik

realmarket Apache 2.0 lisanslı açık kaynak yazılımdır. Kurum kodu inceleyebilir, kendi
sunucusunda çalıştırabilir, değiştirebilir ve gerekirse geliştiriciden bağımsız
sürdürebilir. Her sürümün değişiklikleri `CHANGELOG.md` dosyasında, test sonuçları
`evals/reports/` klasöründedir. Yazılımın kendi test paketi 340'ı aşkın otomatik testten
oluşur ve ağ bağlantısı olmadan çalışır.
