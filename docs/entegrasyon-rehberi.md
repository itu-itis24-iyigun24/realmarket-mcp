# Aracı kurumlar için entegrasyon rehberi

Bu rehber, realmarket'i kendi mobil uygulamasındaki yapay zekâ asistanına bağlamak isteyen
aracı kurumun ürün, BT ve veri ekipleri içindir. Veri servisinin (adaptörün) teknik sözleşmesi
[`adapter-api.md`](adapter-api.md) belgesindedir; sunucu, model testi ve denetim kaydının
ayrıntıları bu rehberdedir.

## Ne işe yarar

Müşteri uygulamadaki asistana "Portföyüm nasıl?", "THYAO enflasyonu yendi mi?", "EREGL ucuz
mu?" gibi sorular sorar. Asistan cevabı kendi bilgisinden değil, realmarket'in hesapladığı
rakamlardan kurar:

- getiriler, enflasyona göre reel getiri, dolar, altın, mevduat, konut ve asgari ücrete göre
  kıyaslar, gerçek alım satımlardan portföy analizi (bedelsiz ve temettü dahil), değerleme
  oranları ve sektör kıyası, finansal tablolar (TMS 29 dahil), olay tepkileri;
- her rakamın kaynağı, dönemi ve veri sürümü; veri kalitesi uyarıları;
- Türkçe olgu cümleleri: her rakam anlamı ve tarihiyle gelir, model onu aktarır;
- veri kalitesi uyarıları, etkiledikleri rakamın yanında: eksik günler, bölünme izleri, boş
  (sıfır hacimli) günler, eski veri, birbiriyle tutmayan finansal tablolar.

Araçlar al, sat, tut önerisi, hedef fiyat, fiyat hareketine neden ya da "ucuz/pahalı" hükmü
üretmez. Müşterilerin sorabileceği biçimde yazılmış 119 soruluk test setinde (Eylül 2026)
beş model ölçüldü: Claude Sonnet 119/119, Gemini 3.5 Flash-Lite ve 3.1 Flash-Lite 118/119,
Claude Haiku 4.5 116/119 doğru cevap verdi; açık kaynak Gemma 4 26B cevapladığı 48 sorunun
44'ünde içerik olarak doğruydu. Hiçbir cevapta tavsiye, fiyat hareketine neden gösterme ya da
ucuz/pahalı hükmü yoktu (`evals/reports/`). Sonuç kurumun modeline ve verisine göre değişir;
kurum kendi modelini 4. adımdaki araçla sınamalıdır.

## Pilot kapsamı

Pilot, Borsa İstanbul hisseleri, BIST endeksleri, yatırım fonları, döviz ve altın içindir;
getiriler TL cinsinden ve TÜFE'ye göre ölçülür. ABD ve diğer yurt dışı hisseler pilotun
dışındadır: adaptör bunları sunmaz, sunsa bile yurt dışı enflasyon kaynağı ayarlanmadığı
için reel getiri araçları "bu hizmette yok" der.

## Mimari

```
Müşteri → kurumun uygulaması → kurumun yapay zekâ modeli → realmarket (MCP sunucusu)
                                                               │
                         ┌─────────────────────────────────────┼─────────────────────┐
                 kurumun veri servisi (adaptör)          TCMB EVDS            haberler (isteğe bağlı)
                 lisanslı fiyat, temettü, bedelsiz,      enflasyon, mevduat,  kurumun KAP/haber akışı
                 finansallar, sektör listesi             konut fiyatları      ya da GDELT
```

- Fiyat verisi kurumun ağından çıkmaz: realmarket veriyi saklamaz, her soruda adaptörden okur.
- Müşterinin sorusu ve araçların sonuçları (portföyü dahil) kurumun seçtiği yapay zekâ
  modeline gider. Modelin nerede çalıştığı ve kişisel verinin, gerekiyorsa yurt dışına,
  aktarılmasının hukuki dayanağı kurumun kararıdır.
- Adaptörle çalışırken realmarket kendiliğinden yurt dışındaki bir kaynağa bağlanmaz: yalnızca
  adaptöre ve kurumun ayarladığı kaynaklara (TCMB EVDS gibi) gider. Ayrıntı 3. adımda.
- Model kurumun seçimidir; tool calling destekleyen her model MCP ile bağlanabilir.

## Adım adım

### 1. Veri servisini (adaptörü) yazın

Kurumun elindeki veri kaynağının önüne, istediğiniz dilde küçük bir HTTP servisi koyarsınız.
Elinizde bir veri API'si varsa iş büyük ölçüde bir biçim çevirisidir.

| Uç | Zorunlu mu | Ne sağlar |
|---|---|---|
| `/meta` | Evet | Kaynak adı, lisans satırı, altın ve kur sembolleri, endeks |
| `/search` | Evet | Sembol ve şirket adı arama |
| `/bars` | Evet | Günlük fiyatlar |
| `/bars` içinde `dividends`, `splits`, `price_close` | Hayır | Temettü verimi, getirinin temettü payı, bedelsizlerin portföye otomatik uygulanması |
| `/financials` | Hayır | Finansal tablolar, F/K, PD/DD |
| `/peers` | Hayır | Sektör kıyası: "ucuz mu?" diye soran müşteriye hüküm yerine şirketin PD/DD'sini benzerleriyle yan yana verir |
| `/news` | Hayır | KAP bildirimleri ve haberler |

Hangi isteğe bağlı uçları sunduğunuzu `/meta` içinde `endpoints` alanıyla bildirin
(ör. `["financials", "peers"]`). realmarket modele yalnızca verisini sunduğunuz araçları
gösterir: `financials` yoksa değerleme ve finansal tablo araçları, `news` yoksa haber aracı
listede olmaz. F/K, PD/DD ya da haberleri modelinize kendi platformunuzdan veriyorsanız bu
uçları hiç yazmanıza gerek yoktur.

Başlangıç noktası: `examples/adapter/serve_files.py` (yalnızca standart kütüphane; dosyadan
okuyan kısımları kendi kaynağınıza yönlendirirsiniz).

### 2. Adaptörü test edin

```bash
REALMARKET_HTTP_TOKEN=... realmarket-adapter-check --url https://veri.kurum.internal/realmarket/v1 --symbol THYAO
```

Her uç için GEÇTİ / UYARI / KALDI / ATLANDI raporu verir; atlanan isteğe bağlı bir parça,
hangi özelliğin çalışmayacağını söyler. `/meta`'da bildirip sunmadığınız bir uç KALDI,
sunup bildirmediğiniz bir uç UYARI olarak görünür. Test aracı, realmarket'in çalışırken kullandığı kodla
aynı kodu kullanır: burada geçen üretimde de çalışır.

### 3. realmarket'i çalıştırın

```bash
REALMARKET_PRICE_PROVIDER=http \
REALMARKET_HTTP_URL=https://veri.kurum.internal/realmarket/v1 \
REALMARKET_HTTP_TOKEN=... \
REALMARKET_EVDS_API_KEY=... \
REALMARKET_SERVER_TOKEN=... \
realmarket-mcp --transport http --host 0.0.0.0 --port 8000
```

- `REALMARKET_SERVER_TOKEN`: realmarket'e bağlanan sistemin anahtarı. Anahtarı taşımayan her
  istek reddedilir (401). Yalnızca modelinizi çalıştıran sisteme verin. En az 32 karakter
  olmalıdır; üretmek için:
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Bu anahtar müşterinin
  kimliğini değil, kurumun kendi sisteminin kimliğini doğrular. Anahtar olmadan sunucu
  yalnızca aynı makineden (127.0.0.1) erişilebilir biçimde başlar.

- `REALMARKET_EVDS_API_KEY`: TCMB EVDS anahtarı (enflasyon, mevduat, konut). Anahtar ücretsiz
  alınır; ancak EVDS'nin kullanım koşulları, verinin kaynak gösterilerek kullanılabileceğini
  ve kullanıcılardan bu veri için ücret istenemeyeceğini söyler. Ücretli bir hizmette
  kullanımın bu koşula uygunluğu kurumun değerlendirmesidir. Yalnızca enflasyon için
  alternatif: TÜİK'in TÜFE serisini aylık bir CSV dosyası olarak verin
  (`REALMARKET_CPI_CSV_TR`, sütunlar `month,cpi_index`).
- Haberler adaptörün `/news` ucundan gelir (adaptörle çalışırken varsayılan).
- `REALMARKET_FOREIGN_SOURCES`: adaptörle çalışırken varsayılan olarak kapalıdır. Kapalıyken
  realmarket OECD enflasyonuna, AB şirket raporlarına (ESEF) ve GDELT haberlerine bağlanmaz;
  bir bölgenin enflasyonu için kaynak ayarlanmamışsa (ör. ABD hisseleri için ABD enflasyonu)
  ilgili araç bunu söyleyerek durur. `on` bu kaynakları açar.
- `REALMARKET_AUDIT_LOG`: her araç çağrısının denetim kaydı (aşağıda, "Denetim kaydı").
- Anahtarlar yalnızca ortam ayarlarında durur; hiçbir cevapta ya da kayıtta yazılmaz.

Adaptörle çalışırken realmarket, soruyu soranın kurumun müşterisi olduğunu varsayar:
`check_setup` aracı modele gösterilmez; ayarlanmamış bir veri istendiğinde model müşteriye
"bu hizmette yok" der, ayar ya da kaynak adı söylemez. Hangi ayarın eksik olduğu sunucu
kaydına (log) uyarı olarak yazılır.

#### Ayarların özeti

| Ayar | Ne işe yarar |
|---|---|
| `REALMARKET_PRICE_PROVIDER=http`, `REALMARKET_HTTP_URL`, `REALMARKET_HTTP_TOKEN` | Kurumun veri servisi (adaptör) |
| `REALMARKET_SERVER_TOKEN` | Her HTTP isteğinin taşıması gereken anahtar (en az 32 karakter); sunucuyu 127.0.0.1 dışına açmak için zorunlu |
| `REALMARKET_EVDS_API_KEY` | Güncel TÜFE, TL mevduat faizleri ve konut fiyat endeksi |
| `REALMARKET_CPI_CSV_TR` | TÜFE'yi EVDS yerine aylık bir dosyadan okumak için |
| `REALMARKET_NEWS_PROVIDER` | `http`: haberler adaptörün `/news` ucundan (adaptörle varsayılan); `none`: haber kapalı |
| `REALMARKET_FOREIGN_SOURCES=on` | Anahtarsız yurt dışı kaynaklara izin verir (OECD ve FRED enflasyonu, ESEF, GDELT); adaptörle varsayılan olarak kapalı |
| `REALMARKET_SEC_CONTACT` | ABD şirketlerinin resmi finansal tabloları için iletişim e-postası (pilot kapsamı dışında) |
| `REALMARKET_AUDIT_LOG=/var/log/realmarket/audit.jsonl` | Denetim kaydı: her araç çağrısı için bir satır |
| `REALMARKET_AUDIT_FULL=1` | Denetim kaydına her cevabın tam metnini de yazar |

### 4. Modeli bağlayın ve sınayın

Modelinizi MCP istemcisiyle `http://127.0.0.1:8000/mcp` adresine bağlayın. realmarket
Claude'a bağlı değildir; tool calling destekleyen her model MCP istemcisi üzerinden kullanabilir.
Araç listesi sunucu açılırken adaptörün `/meta` cevabından belirlenir; `endpoints` alanını
değiştirirseniz realmarket'i yeniden başlatın. Sunucu, kullanım talimatlarını bağlantı sırasında
gönderir (kaynağı belirt, veri kalitesi uyarılarını önce söyle, tavsiye verme); bunları canlıda
da modelin sistem talimatında tutun. Test bu talimatlarla yapılır.

realmarket kendi rakamlarının doğruluğunu garanti eder; modelin bu rakamlarla ne yaptığını
değil. Araç kullanma becerisi modelden modele cevap kalitesinden daha çok değişir. Bu yüzden
modelinizi müşteriye açmadan önce `realmarket-qualify` ile sınayın. OpenAI uyumlu
`/chat/completions` ucu ve tool calling sunan her sunucuyla çalışır (Ollama, vLLM, LM Studio,
barındırılan bir API):

```bash
realmarket-qualify --base-url http://localhost:11434/v1 --model qwen2.5:14b --output rapor.json
```

Test, modele realmarket'in kendi araçları ve talimatlarıyla sabit bir Türkçe soru seti sorar.
Sorular, test sırasında üretilen kurgusal bir şirket (ORNEK) hakkındadır: piyasa verisi, API
anahtarı ya da model sunucusu dışında ağ bağlantısı gerekmez ve her kurum aynı soruları çalıştırır.
Her cevap otomatik kontrol edilir:

| Kontrol | Ne zaman kalır |
|---|---|
| `tools_used` | Model, sorunun gerektirdiği aracı çağırmak yerine hafızasından cevap verdiyse |
| `figure:<alan>` | Aracın döndürdüğü ana rakam (ör. reel getiri) cevapta yoksa |
| `no_unsupported_figures` | Cevapta hiçbir araç sonucunda olmayan bir rakam varsa: uydurulmuş, yanlış hesaplanmış ya da aracın bilerek vermediği bir oran (başka rakamlardan hesaplanmış bir F/K) |
| `no_advice` | Cevap alım, satım ya da tutma öneriyorsa |
| `no_causal_claims` | Cevap bir fiyat hareketini bir nedene bağlıyorsa |
| `no_reasoning_in_answer` | Cevap metni modelin düşünme bloğunu içeriyorsa (`<think>…</think>`, `<thought>…</thought>`); müşteri bunu görür. Model sunucusunda kapatın ya da uygulamada ayıklayın. Rakamlar yalnızca görünen cevapta kontrol edilir |

Rakamlar Türkçe ve İngilizce yazımla okunur (`1.234,5` / `1,234.5`); yüzdeler aracın
kesirleriyle, bin, milyon ve milyar cinsinden tutarlar tam rakamlarla eşleştirilir. Kontroller
bilerek katıdır: kalan bir kontrolü, bir insanın okuması gereken bir cevap olarak görün.

- Hız sınırı, aşırı yüklenmiş sunucu ya da zaman aşımında istek bekleyip yeniden denenir.
  Sunucunun sürekli reddettiği bir soru ÇALIŞMADI (`NOT RUN`) olarak raporlanır; bu, model
  hakkında bir şey söylemez.
- `--interval 6`: dakikada birkaç isteğe izin veren ücretsiz katmanlar için istekleri aralar.
- `--timeout 300`: büyük araç sonuçlarında uzun düşünen yavaş bir yerel model için bir
  cevabı bekleme süresi (varsayılan 120 saniye).
- `--max-minutes` (varsayılan 15): bütün testin süre sınırı; o süreye kadar başlamamış
  sorular ÇALIŞMADI sayılır.
- Her sonuç belli olur olmaz yazdırılır; `--output` raporu her sorudan sonra güncellenir ve
  her soruyu, araç çağrısını ve cevabı JSON olarak içerir.
- Çıkış kodu: her soru geçerse 0, biri kalırsa 1, sunucu hiç kullanılamıyorsa (yanlış adres,
  anahtar ya da model adı) 2, bazı sorular çalışmadıysa 3.

`--live --cases kurum-sorulari.json` kurumun kendi sorularını, ayarlı kaynaklarına (adaptörüne)
karşı çalıştırır. Dosya şu biçimde bir JSON listesidir: `{"id", "question", "expect_tools": [...],
"expect_figures": [{"tool", "path", "label"}]}`. `--api-key-env AD` model sunucusunun
anahtarını o ortam değişkeninden okur.

## Güvenlik

- realmarket'in MCP ucu bir anahtarla korunur (`REALMARKET_SERVER_TOKEN`): anahtarı
  taşımayan istek araçlara ulaşmadan reddedilir. Anahtar olmadan sunucu dış ağa açılmayı
  reddeder. Yine de iç ağda ve kurumun API geçidinin arkasında tutun.
- Adaptöre giden anahtar yalnızca `Authorization` başlığında gönderilir, yönlendirmelerde
  aktarılmaz, kaydedilmez.
- Adaptörden gelen her cevap sıkı doğrulanır; bozuk veri onarılmaz, uç ve sorun adıyla hataya
  döner.
- Haber başlıkları modele talimat olarak değil, veri olarak verilir.

## Denetim kaydı

`REALMARKET_AUDIT_LOG` ayarlıysa her araç çağrısı, kurumun kendi sunucusundaki o dosyaya bir
JSON satırı olarak eklenir. Kurum böylece asistana sonradan neyin verildiğini gösterebilir:

```json
{"time": "2026-09-27T12:00:03.114Z", "server_version": "0.1.4", "tool": "get_valuation",
 "arguments": {"symbol": "BIMAS.IS", "price_symbol": null}, "outcome": "ok", "error_code": null,
 "duration_ms": 842.6,
 "provenance": [{"provider": "adapter:acme-feed", "dataset": "daily_bars", "symbols": ["BIMAS.IS"],
   "period_start": "2026-09-06", "period_end": "2026-09-25", "retrieved_at": "2026-09-27T12:00:02Z",
   "data_version": "sha256:…"}, …],
 "quality_flags": ["warning:no_tms29_trailing_earnings"],
 "response_sha256": "…"}
```

- `arguments`, aracın varsayılanlarla doldurulmuş kendi parametreleridir; çağrı aynen
  tekrarlanabilir. `data_version`, her rakamın geldiği verinin tam sürümünü belirtir.
- `response_sha256`, modelin aldığı cevap metninin SHA-256 özetidir. Kurumun uygulaması da
  cevabı saklıyorsa ikisi eşleştirilebilir.
- `REALMARKET_AUDIT_FULL=1` tam cevabı da saklar.
- Ayarlar, API anahtarları ve token'lar asla yazılmaz. Argümanlar müşterinin portföy
  tutarlarını içerebilir: dosyanın saklama süresi, erişim yetkisi ve yenilenmesi kurumun
  sorumluluğundadır.
- Dosyaya yazılamazsa (yol, yetki, disk) araç kayıtsız cevap vermek yerine hata döner.
- Kayıt, araçların döndürdüğünü tutar; modelin müşteriye yazdığını değil. Kurumun uygulaması
  son cevabı bu kaydın yanında saklamalıdır.

## Cevapları müşteriye göstermek

Kurumun arka ucu müşteriye yalnızca modelin son cevabını gönderir. Bazı modeller düşünme
metnini cevabın içine yazar (`<think>…</think>`, `<thought>…</thought>`); bunu model
sunucusunda kapatın ya da cevap arka uçtan çıkmadan ayıklayın. `realmarket-qualify` bunu yapan
bir modeli raporlar (`no_reasoning_in_answer`); denetim kaydı da araçların döndürdüğünü,
uygulamanın sakladığı cevabın yanında tutar.

## Tahmini iş yükü

| İş | Kim | Tahmini süre |
|---|---|---|
| Zorunlu üç uç (`/meta`, `/search`, `/bars`) | Kurumun bir geliştiricisi | Birkaç gün |
| Temettü, bedelsiz, finansallar, sektör listesi | Aynı geliştirici | Bir hafta civarı, verinin hazırlığına bağlı |
| Sunucu kurulumu, API geçidi, izleme | BT | Birkaç gün |
| Modelin sınanması ve uygulamaya bağlanması | Ürün ve BT | Bir-iki hafta |

Süreler kaba tahmindir; kurumun veri kaynağının hazırlığına göre değişir.

## Destek

realmarket açık kaynaktır ve geliştiricisi tarafından sürdürülür. Geliştirici kurumlara şunları da
sunar:

- **Pilot:** kurumun veri servisini ve modelini bağlamak, model testini çalıştırmak ve denetim
  kaydını kurumun uyum ekibiyle birlikte incelemek.
- **Entegrasyon desteği:** kurumun veri akışları için adaptörü yazmak ya da incelemek;
  asistan için Türkçe rapor şablonları.
- **Bakım:** kaynaklar değiştiğinde güncellemeler (ör. yeni stopaj oranı ya da asgari ücret
  kararı) ve kurumun bildirdiği hataların düzeltilmesi.

Sorular ve hata bildirimleri GitHub deposunda açılabilir. Pilot ve destek koşulları her kurumla
ayrıca kararlaştırılır.

## Hukuk ve uyum birimleri için

Ürünün ne yapıp ne yapmadığı, veri akışı, denetim kaydı ve test sonuçları tek belgede:
[`uyum-dosyasi.md`](uyum-dosyasi.md).
Pilotun süresi, aşamaları ve başarı ölçütleri: [`pilot-protokolu.md`](pilot-protokolu.md).

## Kurumda kalan sorumluluklar

- Verinin lisansı ve doğruluğu (realmarket veriyi denetler ama kaynağın yerine geçmez). Borsa
  verisi lisansının, verinin hesaplamalarda ve yapay zekâ cevaplarında kullanımını (türetilmiş
  veri) kapsayıp kapsamadığı da buna dahildir.
- Müşteri ekranında asistanın bir yapay zekâ olduğunun ve cevabın yatırım danışmanlığı
  olmadığının belirtilmesi; cevaplardaki kaynakların gösterilmesi.
- Kişisel verilerin (müşterinin portföyü ve soruları) işlenmesi, denetim kaydının saklama
  süresi ve erişim yetkisi, modele aktarımın KVKK açısından dayanağı.
- Modelin seçimi ve sınanması; müşteriye gösterilen metin ve uyarılar.
- SPK mevzuatı açısından değerlendirme: araçlar tavsiye üretmez, ancak ürünün mevzuata
  uygunluğu kurumun hukuk ve uyum birimlerinin kararıdır.
- Kendi API geçidinde kimlik doğrulama, istek sınırlama ve kayıt.

realmarket Apache-2.0 lisanslıdır: lisans ve bildirimler korunarak kullanılabilir,
değiştirilebilir ve ticari olarak sunulabilir.
