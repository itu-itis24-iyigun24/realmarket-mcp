# realmarket pilot protokolü

Bir aracı kurumla yapılacak ücretsiz pilotun çerçevesi: süre, kapsam, kim ne yapar, neyin
ölçüleceği ve pilotun nasıl biteceği. Ayrıntılar ilk görüşmede kurumla birlikte netleşir.

## Amaç

realmarket'in kurumun kendi verisi ve kendi seçtiği yapay zekâ modeliyle doğru çalıştığını,
tavsiye üretmediğini ve kurumun altyapısına makul bir işle bağlanabildiğini, **gerçek
müşterilere açılmadan** kurum içinde göstermek.

## Kapsam

- **Varlıklar:** Borsa İstanbul hisseleri, BIST endeksleri, yatırım fonları, döviz ve altın.
  Getiriler TL cinsinden ve TÜFE'ye göre ölçülür. Yurt dışı hisseler kapsam dışıdır.
- **Kullanıcılar:** Yalnızca kurumun belirlediği çalışanlar. Asistan müşterilere açılmaz.
- **Veri:** Piyasa verisi kurumun kendi lisanslı kaynağından gelir. Gerçek müşteri
  portföyleri kullanılmaz; test kullanıcıları hayalî ya da maskelenmiş portföylerle çalışır.
- **Ortam:** Kurumun kendi test ortamı. realmarket kurumun sunucusunda çalışır.
  Geliştiricinin kurumun sistemlerine erişimi olmaz.

## Süre ve aşamalar (6 hafta)

| Hafta | İş | Çıktı |
|---|---|---|
| 1 | Açılış görüşmesi; kapsam, test kullanıcıları ve ortam netleşir. Kurum adaptörün zorunlu üç ucunu (`/meta`, `/search`, `/bars`) yazar. | Zorunlu uçlarda `realmarket-adapter-check` KALDI vermez |
| 2 | Adaptörün isteğe bağlı uçları (temettü, bedelsiz, finansallar, sektör listesi, haberler); realmarket kurulumu: sunucu anahtarı, denetim kaydı, API geçidi. | Adaptör denetim raporu; çalışan kurulum |
| 3 | Kurumun modeli bağlanır ve `realmarket-qualify` ile sınanır: yerleşik sorular ve 119 soruluk set. | Model test raporu |
| 4–5 | Kurum içi kullanım: test kullanıcıları kendi sorularını sorar. Uyum birimi denetim kaydından örnekleri haftalık inceler. Bulunan sorunlar düzeltilir. | Haftalık kısa durum notu; düzeltmeler |
| 6 | Ortak değerlendirme. | Değerlendirme raporu ve devam kararı |

## Kim ne yapar

**Kurum**

- **Veri ekibi:** adaptörü yazar. Zorunlu uçlar birkaç gün, isteğe bağlı uçlar yaklaşık bir
  hafta sürer.
- **BT:** sunucuyu, API geçidini ve anahtarları kurar.
- **Ürün:** test kullanıcılarını belirler ve modeli seçer.
- **Uyum:** uyum dosyasını (`docs/uyum-dosyasi.md`) ve denetim kaydı örneklerini
  değerlendirir.

**Geliştirici**

- Kurulum ve adaptör için destek verir, adaptör kodunu inceler.
- Model testlerini birlikte yürütür ve raporlar.
- Haftalık görüşmeye katılır.
- Pilotta bulunan hataları düzeltir.
- Değerlendirme raporunu yazar.

## Başarı ölçütleri

Pilotun başında kurumla birlikte teyit edilir. Önerilen ölçütler:

1. **Adaptör:** Zorunlu uçlarda `realmarket-adapter-check` hatasız geçer; bildirilen isteğe
   bağlı uçlar sunulur.
2. **Model:** 119 soruluk sette okumada en az %95 doğru cevap.
3. **Tavsiye yok:** Model testinde ve kurum içi kullanımda, tavsiye, fiyat hareketine neden
   gösterme ya da ucuz/pahalı hükmü içeren cevap sayısı **sıfır**. Bu ölçüt pazarlık konusu
   değildir; tek bir örnek bile düzeltme gerektirir.
4. **Kapsam dışı sorular:** Politika faizi, tahvil faizi, teknik göstergeler gibi kapsam dışı
   sorularda model hafızasından rakam vermez, "bu hizmette yok" der.
5. **Kurum içi kullanım:** Test kullanıcılarının sorularından örneklem alınır, uyum birimi
   her cevabı doğru, eksik ya da hatalı diye işaretler; sonuç raporda yer alır.
6. **İşletim:** Yanıt süreleri ve hatalar denetim kaydından ölçülür ve raporlanır. Kabul
   eşikleri kurumun beklentisine göre belirlenir.

## Veri ve gizlilik

- Gerçek müşteri verisi pilotta kullanılmaz.
- Geliştiriciye kişisel veri gönderilmez. Destek için paylaşılan kayıt örnekleri kurum
  tarafından anonimleştirilir.
- Taraflar pilot sırasında öğrendikleri bilgileri gizli tutar. Kurumun adı, yazılı izni
  olmadan referans olarak kullanılmaz.

## Ücret, garanti ve bitiş

- **Ücret:** Pilot ücretsizdir. Pilot sonrası kullanım, destek ve bakım ayrıca konuşulur.
- **Garanti:** realmarket Apache 2.0 lisanslı açık kaynak yazılımdır ve olduğu gibi
  sunulur. Pilot süresince müşterilere açılmadığı için müşteriye yönelik bir risk doğmaz.
- **Bitiş:** Taraflardan biri pilotu dilediği an sonlandırabilir. Pilot bitince kurum
  yazılımı kullanmaya devam edebilir ya da kaldırabilir; kod ve veri kurumda kalır.
- **Karar:** Değerlendirme raporu üç seçenekten birini önerir: canlıya hazırlık, değişiklikle
  ikinci aşama ya da sonlandırma.

## İlgili belgeler

- Ürün ve uyum: [`uyum-dosyasi.md`](uyum-dosyasi.md)
- Teknik entegrasyon: [`entegrasyon-rehberi.md`](entegrasyon-rehberi.md) ve
  [`adapter-api.md`](adapter-api.md)
- Test raporları: `evals/reports/`
