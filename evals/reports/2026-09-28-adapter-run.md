# Model kontrolü, 28 Eylül 2026: veri adaptörü üzerinden 119 soru

**Soru.** Kendi verisini adaptör üzerinden bağlayan bir kurum, Yahoo yolundakiyle aynı
cevapları alıyor mu? Bu çalıştırma için adaptör API'sine `/bars` içinde temettüler, bedelsizler
ve işlem görmüş kapanışlar ile isteğe bağlı bir `/peers` ucu eklendi; geri kalan her şey aynı.

**Kurulum.** Kurum tarzı bir veri seti (semboller, bir Türk aracı kurumunun veri akışındaki
adlarıyla: `THYAO`, `XU100`, `USDTRY`, `XAUUSD`; 26 seri, temettüler, bedelsizler, finansal
tablolar ve benzer şirket listeleri) tek bir Yahoo anlık görüntüsünden oluşturuldu ve
`examples/adapter/serve_files.py` ile sunuldu. Veri seti depoya konmadı: realmarket piyasa
verisi dağıtmaz. `realmarket-adapter-check`, zorunlu kontrollerin hepsini ve verinin kapsadığı
isteğe bağlı kontrollerin hepsini geçti. Ardından Claude Haiku 4.5 aynı 119 soruyu, aynı
gruplarla, `REALMARKET_PRICE_PROVIDER=http` ile cevapladı.

## Sonuç

| | Yahoo yolu (2. tam çalıştırma) | Adaptör yolu |
|---|---|---|
| Otomatik kontrolleri geçti | 114 / 119 | 113 / 119 |
| Okumada doğru | 115 / 119 | 116 / 119 |
| Tavsiye, fiyat hareketine neden gösterme, ucuz/pahalı hükmü | 0 | 0 |

Aynı çağrıların iki yolda doğrudan karşılaştırılması aynı rakamları verdi (THYAO'nun PD/DD'si
ve alt sektör kıyası, BIMAS'ın bir portföye uygulanan bedelsizi, GARAN'ın temettü verimi).

Haiku'nun üç hatası: `compare_assets` ile dolar cinsinden altını lira cinsinden hisseyle
karşılaştıran bir KCHOL-altın cevabı (para birimlerinin farklı olduğunu söylüyor ama yine de
bir kazanan adı veriyor) ve olgu cümlelerinin (araçların döndürdüğü Türkçe cümleler) başka bir
biçimde verdiği bir farkı kendisi hesaplayan iki cevap. Diğer üç otomatik başarısızlık testin
kendisinden: kayıt bayrağı olmadan yapılan çağrılar, "yok" ile biten bir ret ve önceki sorunun
portföyüyle cevaplanan bir soru.

## Çalıştırmanın bulduğu sorunlar ve yapılan değişiklikler

1. **`check_setup`, adaptörle finansal tabloların mevcut olmadığını söylüyordu.** Finansal
   tablo kaynağı olarak yalnızca Yahoo'yu biliyordu; bu yüzden adaptörle olgu cümleleri
   "Türkiye ve diğer piyasalar için yok" diyordu ve Haiku, adaptörün cevaplayabileceği dört finansal tablo ve
   değerleme sorusunu reddetti. Finansal tablolar artık, fiyat kaynağı açıkken (Yahoo, adaptör,
   yerel dosyalar) o kaynaktan geliyor olarak bildiriliyor. Dördünün yeniden çalıştırılması:
   doğru.
2. **Kapalı bir güne tarihlenen işlem önceki kapanışı kullanıyordu.** 2024-06-01 (Cumartesi)
   olarak yazılan "Haziran 2024", bir alımı 31 Mayıs kapanışından fiyatlıyordu; böylece aynı
   portföy, tarihin nasıl yazıldığına göre +20.340 TL ya da +21.177,50 TL veriyordu. Kapalı bir
   günde fiyatsız girilen alım ya da satım artık bir sonraki seansta gerçekleşiyor ve olgu
   cümleleri bunu söylüyor. Yeniden çalıştırma: adaptör ve Yahoo yolları aynı sonucu veriyor.
3. **Temettüler girilmemişti; model onları kendisi topluyordu.** Hesap düzeyindeki olgu
   cümlesi artık temettülerin toplamını, temettüler dahil sonuçla birlikte söylüyor.

## Sonrasında: farklı para birimlerindeki varlıklar

`compare_assets` artık farklı para birimlerinde fiyatlanan varlıkları tek bir para biriminde
ölçüyor (biri TRY ise TRY) ve sıralamayı orada yapıyor; kur yoksa para birimleri arasında
sıralama yapmıyor. Bir varlığın dolar cinsinden getirisini veren reel getiri olgu cümlesi artık
varlığın adını söylüyor: Haiku, XU100 için verilen "…dolar cinsinden getiri -%0,87" cümlesini doların kendi
getirisi olarak okumuştu. Etkilenen iki sorunun yeniden çalıştırılması (KCHOL mu altın mı;
altın, dolar ve BIST 100): ilk düzeltmeden sonra Sonnet 2 / 2 ve Haiku 3 / 4, kaçırılan cevap o
dolar yanlış okumasıydı; ikinci düzeltmeden sonra Haiku 4 / 4 (TL cinsinden altın +%32,0, dolar
+%17,8, BIST 100 +%16,8; üç yılda TL cinsinden altın +%311,9, KCHOL +%71,9;
`compare_real_return`'ün verdiği rakamın aynısı).
