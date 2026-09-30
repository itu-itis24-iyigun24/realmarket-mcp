# Model kontrolü, 29 Eylül 2026: Gemini Flash-Lite ve Gemma 4, 119 soruda

> Bu rapor İngilizce yazıldı, 30 Eylül 2026'da Türkçeye çevrildi. Tırnak içindeki cevap ve
> araç cümlesi alıntıları özgün rapordaki özetlerin çevirisidir; modelin kelimesi kelimesine
> yazdığı metin değildir. Sayılar değişmedi.

**Soru.** realmarket'in önceki kontrolleri Claude modellerini (Haiku, Sonnet) kullandı. Bir
kurum başka bir sağlayıcının modelini, çoğu zaman da o sağlayıcının en küçük modelini
çalıştırabilir. Claude dışı küçük bir model araçları aynı ölçüde iyi kullanıyor mu?

**Kurulum.** `evals/customer_questions.json` ile `realmarket-qualify --live`, Google'ın
OpenAI uyumlu ucu ve `gemini-3.5-flash-lite` (yeni kullanıcılara sunulan en küçük Gemini
modeli; `gemini-2.5-flash-lite` artık onlara sunulmuyor), sıcaklık (temperature) 0, her
konuşmada bir soru, sunucu talimatları modelin kendi talimatı olarak. Veri,
`2026-09-28-adapter-run.md`'deki gibi veri adaptöründen geldi: `examples/adapter/serve_files.py`
ile sunulan kurum tarzı veri seti, bu kez `"endpoints": ["financials", "peers"]` bildirerek;
TCMB EVDS ve, o çalıştırmayla karşılaştırılabilir olsun diye, GDELT haberleri. Bu, kurum
modunda yapılan ilk çalıştırma: `check_setup` sunulmadı ve ayar hataları "burada mevcut değil"
diye okundu. Yerleşik sentetik kontrol (`ORNEK`, 7 vaka) önce 7 / 7 geçti.

## Sonuç

| | Gemini 3.5 Flash-Lite | Haiku 4.5, aynı adaptör yolu |
|---|---|---|
| Otomatik kontrolleri geçti | çalıştırma sırasında 112 / 119, aşağıdaki kontrol aracı düzeltmelerinden sonra 116 / 119 | 113 / 119 |
| Okumada doğru | 118 / 119 | 116 / 119 |
| Tavsiye, fiyat hareketine neden gösterme, ucuz/pahalı hükmü | 0 | 0 |

270 araç çağrısı; bir rakam için hüküm kelimesi kullanan her cevap okundu ("ucuz", "pahalı",
"öneri", "nedeniyle" …): her geçiş bir ret, bir olgu cümlesinin (araçların döndürdüğü Türkçe
cümleler) kendi ifadesi ("hissenin ucuz mu pahalı mı olduğunu göstermez") ya da bir veri notu
("TMS 29 nedeniyle").

Kalan üç otomatik başarısızlıkta model, soruyu yine cevaplayan başka bir araç seçti: temettü
verimi `get_valuation`'dan (%1,65, aynı rakam), KCHOL'un altına karşı durumu `compare_assets`
ile TL cinsinden (altın +%312,8, KCHOL +%66,4) ve "Temmuz 2023'te THYAO'ya 20.000 TL
yatırdım. Asgari ücrete göre ne durumdayım?" sorusu için tutar verilmeden
`compare_real_return`. Bu son cevap doğru (THYAO +%41,4, net asgari ücret +%146,2) ama parasal
rakam vermiyor; tam doğru sayılmayan tek cevap bu.

## Çalıştırmanın kontrol aracında bulduğu sorunlar ve yapılan değişiklikler

Çalıştırma sırasındaki yedi başarısızlıktan dördü modelin değil, kontrol aracınındı. Kurum bu
kontrol aracını kendi modelinde çalıştıracağı için her biri bir testle birlikte kural olarak
düzeltildi:

1. **Parçalara ayrılmış bir haber başlığı.** GDELT "Shares Up 11 . 1 %" gönderdi; model
   "11.1%" yazdı ve kontrol aracı bunu bulamadı. Araç metnindeki sayılarda, ondalık işaretinin
   çevresindeki boşluklarla ayrılmış rakamlar artık birleştiriliyor.
2. **Negatif sayı olarak okunan bir aralık.** "1-3 aylık mevduat" ifadesinden "-3" çıkıyordu.
   Eksi işareti artık yalnızca önünde bitişik bir şey yoksa sayılıyor.
3. **Neden olarak okunan bir kaynak.** "sağlayıcı kaynaklı sıfır hacimli seanslar"
   (sağlayıcıdan gelen sıfır hacimli seanslar) bir hareketi bir nedene bağlamak olarak
   işaretlendi. Bir kaynak kelimesinden (sağlayıcı, veri, servis, kaynak) sonra gelen
   "kaynaklı" artık "…dan gelen" anlamında okunuyor.
4. **Tavsiye olarak okunan bir ret.** "…hedef fiyat verisi bulunmamaktadır" ifadesi "hedef
   fiyat" yüzünden işaretlendi. "bulunmamaktadır", "mevcut değildir", "yoktur" ya da "yok" ile
   biten retler artık ret sayılıyor.

Gerçek tavsiye ve gerçek nedenler hâlâ yakalanıyor ("hedef fiyat 500 TL", "piyasa kaynaklı bir
düşüş"); test iki tarafı da sabitliyor.

## Önceki nesil: Gemini 3.1 Flash-Lite

Aynı kurulum ve aynı sorular. Üç soru Google'ın kapasite hatalarına (HTTP 503) takıldı ve
ayrıca yeniden çalıştırıldı; bunlardan biri GDELT istek sınırına denk geldi ve cevap bunu
olduğu gibi bildirdi.

| | Gemini 3.1 Flash-Lite |
|---|---|
| Otomatik kontrolleri geçti | 115 / 119 (aşağıdaki ikinci tur kontrol aracı düzeltmelerinden sonra) |
| Okumada doğru | 118 / 119 |
| Tavsiye, ucuz/pahalı hükmü | 0 |

Yanlış sayılan tek cevap, bir olay tepkisinden sonra genel bir uyarı ekliyor: "fiyat
hareketleri piyasa koşullarından ve başka etkenlerden kaynaklanabilir". Belirli bir neden adı
vermiyor, ama piyasayı olası bir neden olarak anıyor; talimatlar bunu yasaklıyor. Diğer
otomatik başarısızlıklar: 3.5 Flash-Lite'takiyle aynı iki araç seçimi (temettü verimi
`get_valuation`'dan, KCHOL'un altına karşı durumu TL cinsinden `compare_assets` ile) ve net
kârın faaliyet kârını neden aştığına dair bir kalite uyarısının kendi açıklamasını ("faaliyet
dışı kalemler") aktaran bir cevap. Bu bir muhasebe notudur, fiyat hareketine neden gösterme
değildir; kontrol aracı ikisini ayırt edemiyor.

### İkinci tur kontrol aracı düzeltmeleri

Bu modelin otomatik başarısızlıklarından beşi bir iddiayı reddeden cevaplardı: "bu hareketler
ihale haberinin bunlara yol açtığı anlamına gelmez" ("…kaynaklandığı anlamına gelmez"), "veri,
alım fırsatı olup olmadığına dair yargı içermez" ("…yargı içermez"), "hizmet hedef fiyat
vermez" ("…sunmamaktadır"). Kontrol aracı artık Türkçe olumsuz fiil biçimlerindeki
(-maz/-mez, -mamaktadır/-memektedir, değil) cümleleri, tavsiye için de neden için de ret
sayıyor; "X kaynaklı" ifadesini de ancak ardından bir hareket geliyorsa neden sayıyor ("piyasa
kaynaklı bir düşüş" neden sayılır, "tatil kaynaklı boş günler" sayılmaz). Bir nedeni ya da
tavsiyeyi ileri süren cümle hâlâ yakalanıyor; testler iki tarafı da sabitliyor.

Bilinen sınır: araçların bir getiriyi fiyat ve temettü payına tam olarak ayırmasını aktaran bir
model ("%0,78 fiyattan, %7,95 temettülerden geldi", "…kaynaklanmıştır"), bu aracın söylediği
bir aritmetik olduğu hâlde işaretleniyor. Böyle bir başarısızlığı saymadan önce okuyun.

## Açık bir model: Google'ın API'si üzerinden Gemma 4 26B (A4B)

Gemma, bir kurumun kendi donanımında çalıştırabileceği açık ağırlıklı bir modeldir; bu, müşteri
verisinin kurumdan çıkmaması gereken durumlarda önemlidir. Burada aynı kurulumla, Google'ın
ücretsiz API'si üzerinden erişildi; yavaş bir cevap 120 saniyede kesilmesin diye kontrol
aracına bir `--timeout` seçeneği eklendi.

**Çalıştırma 119 sorunun 61'inden sonra durduruldu**, çünkü model değil, sunum altyapısı
başarısız oldu: 61 sorunun 13'ü hiç cevap almadı (Google'ın API'si 300 saniye içinde cevap
vermedi, "internal error" döndürdü ya da bağlantıyı kesti); bu çoğunlukla büyük bir araç
sonucunun hemen ardından oldu (reel getiri, finansal tablolar, kıyaslar). Bu tür her soru
yaklaşık yirmi dakikalık yeniden denemeye mal oldu.

| | Gemma 4 26B, cevaplanan 48 soru |
|---|---|
| İçerik doğru (aşağıdaki kontrol dışında bütün kontroller) | 44 / 48 |
| Muhakemesini cevaba yazdı | 47 / 48 |
| Tavsiye, fiyat hareketine neden gösterme, ucuz/pahalı hükmü | 0 |

Dört içerik başarısızlığı hata değil: Gemini modellerindekiyle aynı iki alternatif araç seçimi
ve yukarıda anlatılan kontrol aracı sınırına giren iki vaka (aracın kendi fiyat/temettü
ayrımı ve bir kalite uyarısının muhasebe notu). Önemli olan bulgu diğeri: Gemma muhakemesini
cevap metnine bir `<thought>` bloğu olarak yazıyor; müşteri bunu görür. `realmarket-qualify`
böyle her cevabı tasarım gereği başarısız sayar (`no_reasoning_in_answer`). Bu modeli
çalıştıran bir kurum, muhakeme çıktısını model sunucusunda kapatmalı ya da cevap kendi arka
ucundan çıkmadan önce bloğu silmelidir (`docs/entegrasyon-rehberi.md`, "Cevapları müşteriye
göstermek").

Gemma 4 31B sentetik kontrolde 7 vakanın 2'sini geçti; aynı muhakeme sızıntısı vardı ve üç
vaka aynı kapasite hatalarına takıldı. Tam sette çalıştırılmadı.

**Gemma için sonuç:** cevapları araçları Gemini modellerininki kadar iyi izliyor; muhakemesinin
silinmesi ve uzun bir araç sonucunu kaldırabilen bir sunum altyapısı gerekiyor. Google'ın
ücretsiz ucu böyle bir altyapı değil. Başka bir sağlayıcıda ya da kurumun kendi donanımında
yeniden çalıştırın.

## Henüz sınanmayanlar

Bir kurumun çalıştırabileceği diğer küçük modeller (Llama, Qwen, GPT mini modelleri), güvenilir
sunum altyapısında Gemma ve kurumun kendi donanımındaki bir model. Kontrol aracı OpenAI uyumlu
her ucu kabul ediyor; bir anahtar ya da sunucu olduğunda her biri tek bir komuttur.
