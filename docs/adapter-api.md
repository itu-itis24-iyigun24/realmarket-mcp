# Veri adaptörü API'si, sürüm 1

Veri adaptörü (veri servisi), realmarket'in Yahoo Finance yerine kurumun kullanım lisansı
olan piyasa verisini (borsa veri akışı, veri sağlayıcı, kurum içi veritabanı) kullanmasını
sağlar. Adaptör, herhangi bir dilde yazılmış küçük bir HTTP servisidir; üç zorunlu JSON ucuna
(ve üç isteğe bağlı uca: finansal tablolar, sektördeki benzer şirketler ve haberler) cevap verir. realmarket her
cevabı sıkı doğrular; hiçbir şey onarılmaz ya da tahmin edilmez. Yerel dosyaları sunan,
çalıştırılabilir bir örnek
[`examples/adapter/serve_files.py`](../examples/adapter/serve_files.py) dosyasındadır.

realmarket'i şu ayarlarla yapılandırın:

| Değişken | Değer |
|---|---|
| `REALMARKET_PRICE_PROVIDER` | `http` |
| `REALMARKET_HTTP_URL` | adaptörün temel adresi, ör. `https://marketdata.internal/realmarket/v1` |
| `REALMARKET_HTTP_TOKEN` | isteğe bağlı; `Authorization: Bearer <token>` olarak gönderilir, asla kaydedilmez ya da geri döndürülmez, adaptör yönlendirme yaptığında aktarılmaz |

Bütün uçlar `GET`'tir ve `application/json` döndürür. Tarihler `YYYY-MM-DD` biçimindedir.
Sayılar JSON sayısıdır (metin değil); kaynakta olmayan bir değer `null`'dır, asla `0` ya da
`NaN` değildir. Bilinmeyen bir sembol ya da eksik veri için HTTP 404 döndürün; bunun dışındaki
her hata durumu kullanıcıya adaptörün kullanılamadığı biçiminde bildirilir.

## `GET /meta`

Kaynağı tanımlar. realmarket bunu bir kez okur ve bir saat önbellekte tutar.

```json
{
  "api_version": 1,
  "name": "acme-feed",
  "attribution": "Source: ACME Market Data, licensed to Example Securities.",
  "gold_usd_symbol": "XAUUSD",
  "fx_symbol": "{base}{quote}",
  "benchmarks": {"TRY": "XU100"},
  "endpoints": ["financials", "peers"]
}
```

| Alan | Zorunlu | Anlamı |
|---|---|---|
| `api_version` | evet | `1` |
| `name` | evet | Kısa kaynak adı; her rakam `provider` olarak `adapter:<name>` gösterir |
| `attribution` | hayır | Bu kaynaktan gelen her rakamla birlikte gösterilen kaynak satırı |
| `gold_usd_symbol` | evet | Troy ons başına ABD doları cinsinden altının sembolü |
| `fx_symbol` | evet | Döviz kurları için kalıp: bir `{base}` karşılığında `{quote}` birimi (ör. `USDTRY` = USD başına TRY) |
| `benchmarks` | hayır | Para birimi başına varsayılan endeks; `get_event_reaction` kullanır |
| `endpoints` | hayır, ama önerilir | Adaptörün sunduğu isteğe bağlı uçlar: `financials`, `peers`, `news` değerlerinden herhangi biri (boş liste geçerlidir) |

**Modele hangi araçların sunulacağını `endpoints` belirler.** realmarket bunu açılırken okur:
`financials` yoksa `get_financials` ya da `get_valuation` sunmaz, `news` yoksa `get_news`
sunmaz (kurum başka bir haber kaynağı ya da SEC e-posta adresi ayarlamadıysa). Kurum bu
rakamları modeline başka bir yoldan verebilir; sunulmayan bir araç yanlışlıkla çağrılamaz.
`endpoints` alanını hiç göndermeyen bir adaptör, bu alan yokken olduğu gibi bütün araçları
alır; ucunu sunmadığı araçlar çağrıldığında hata verir. Test aracı bu durumda uyarır. Liste bir
kez okunur; değiştirdikten sonra realmarket'i yeniden başlatın.

## `GET /search?q=<text>&limit=<n>`

Sembolü ya da adı `q` ile eşleşen varlıklar; en iyi eşleşme önce, en fazla `limit` kadar.

```json
{"assets": [
  {"symbol": "THYAO", "name": "Türk Hava Yolları A.O.", "asset_class": "equity",
   "currency": "TRY", "exchange": "BIST"}
]}
```

`asset_class` şunlardan biridir: `equity`, `index`, `fx`, `commodity`, `fund`, `crypto`, `other`.

## `GET /bars?symbol=<s>&start=<date>&end=<date>`

Tek bir sembol için iki tarih arasındaki (iki tarih dahil) günlük fiyat satırları (bar); tarihe
göre artan sırada, her tarih için bir bar.

```json
{
  "symbol": "THYAO",
  "currency": "TRY",
  "adjustment": "split_and_dividend",
  "bars": [
    {"date": "2026-09-24", "open": 290.0, "high": 295.0, "low": 288.0, "close": 292.0, "volume": 1000000},
    {"date": "2026-09-25", "open": 292.0, "high": 300.0, "low": 291.0, "close": null, "volume": 0}
  ]
}
```

- `symbol` istenen sembolle aynı olmalıdır; `currency` ana birimde 3 harfli bir ISO kodudur:
  peni (`GBp`, `GBX`) değil sterlin (`GBP`) gönderin; `ZAR` ve `ILS` için de aynısı geçerlidir.
- `adjustment` serinin fiyat politikasını belirtir, ör. `split_and_dividend` (toplam getiriye
  göre düzeltilmiş), `split` ya da `none`. Her rakamla birlikte gösterilir; veri akışının
  gerçekte ne yaptığını yazın.
- Güncel, henüz bitmemiş seans için bar göndermeyin.

İsteğe bağlıdır; her biri, ona ihtiyaç duyan araçları açar:

```json
{
  "symbol": "THYAO", "currency": "TRY", "adjustment": "split_and_dividend",
  "bars": [{"date": "2026-09-25", "open": 292.0, "high": 300.0, "low": 291.0, "close": 290.75,
            "volume": 1000000, "price_close": 290.75}],
  "dividends": [{"date": "2026-06-02", "amount": 3.8}],
  "splits": [{"date": "2026-05-14", "ratio": 2.0}]
}
```

| Alan | Anlamı | Yoksa |
|---|---|---|
| `bars[].price_close` | `close` temettüye göre de düzeltilmişse, yalnızca bölünmeye göre düzeltilmiş kapanış (işlem gören fiyat) | Getiriler fiyat ve temettü payına ayrılmaz; dönemin en düşük ve en yüksek değerleri temettüye göre düzeltilmiş kapanışlardır |
| `dividends` | Hak kullanım (temettüsüz işlem) tarihine göre hisse başına nakit temettü; serinin para biriminde ve barlarla aynı pay biriminde (sonraki bölünmelere göre düzeltilmiş) | Temettü verimi yoktur; portföyde listelenmemiş temettüler işaretlenmez |
| `splits` | Tarihe göre bölünmeler ve bedelsiz sermaye artırımları: sonraki pay sayısı / önceki pay sayısı (1:1 bedelsiz için `2.0`) | Bedelsizden önce girilmiş bir portföy, kullanıcı bedelsizi listelemedikçe eski pay sayısını korur |

İstenen tarihlere düşen temettü ve bölünmeleri gönderin; tutarlar ve oranlar pozitif
olmalıdır.
- Tatil günlerini tekrarlanan fiyatlarla doldurmayın. Veri akışı bunu yapıyorsa realmarket bu
  barları `placeholder_bars` olarak işaretler.

## `GET /financials?symbol=<s>` (isteğe bağlı)

Finansal tablolar; adaptör bunları sunmuyorsa 404 (realmarket bu durumda bunu söyler).

```json
{
  "currency": "TRY",
  "sector": "Industrials",
  "industry": "Airlines",
  "quarterly": [{"end": "2026-06-30", "values": {"revenue": 7205000000, "gross_profit": 458000000,
                 "operating_income": -88000000, "net_income": 198000000, "total_assets": null,
                 "total_equity": null, "total_debt": 19594000000}}],
  "annual": [{"end": "2025-12-31", "values": {"revenue": 26000000000}}]
}
```

Üst düzeyde isteğe bağlı bir `"shares_outstanding"` alanı (bütün pay grupları, pozitif bir
sayı), `get_valuation`'ın piyasa değerini adaptörün kendi verisinden hesaplamasını sağlar.

Üst düzeyde isteğe bağlı bir `"ttm"` alanı, son rapordan geriye doğru son on iki ayı verir:

```json
"ttm": {"end": "2026-06-30", "values": {"net_income": 29180000000, "revenue": 880000000000}}
```

TMS 29'a tabi Türk şirketleri (bankalar hariç) için F/K ve F/S'nin tek dayanağı budur: bu yılın
başından bugüne + son hesap yılı − geçen yılın aynı dönemi; son ikisi son raporda yeniden
düzenlendiği biçimiyle, hepsi o raporun parasıyla (veri sağlayıcıların yayımladığı "son 12 ay"
rakamı). Bu alan yoksa `get_valuation` bu şirketler için piyasa değeri ve PD/DD verir ama F/K
ya da F/S vermez; çünkü çeyrekleri toplamak ya da son hesap yılını kullanmak çarpanları önemli
ölçüde yanlış çıkarır.

Alanlar: `revenue`, `gross_profit`, `operating_income`, `net_income` (dönem için) ve
`total_assets`, `total_equity`, `total_debt` (dönem sonu itibarıyla); `currency` cinsinden,
tam birimle. Bilinmeyen alanlar yok sayılır. Bankalar dışındaki Türk şirketleri için rakamları
şirketin TMS 29 (enflasyon muhasebesi) kapsamında raporladığı biçimde verin; realmarket TMS 29
kurallarını TRY ile raporlayan şirketlere uygular.

## `GET /peers?symbol=<s>&level=industry|sector` (isteğe bağlı)

Kurumun verisinin `symbol` ile aynı gruba koyduğu şirketler; `get_valuation`'ın "ucuz mu?"
sorusuna cevabı için: şirketin PD/DD'si, aynı gün ve aynı yöntemle ölçülmüş diğerleri arasında
sıralanır. Adaptör benzer şirketleri sunmuyorsa 404 (bu durumda kıyas yapılmaz ve sonuç bunu
söyler). realmarket önce `level=industry` ister; alt sektörde oranı olan başka şirket sayısı
beşten azsa `level=sector` ister.

```json
{
  "industry": "Havayolu",
  "group": "Ulaştırma",
  "market": "Borsa İstanbul",
  "definition": "Piyasa değeri / son bilanço özsermayesi",
  "peers": [
    {"symbol": "THYAO", "name": "Türk Hava Yolları", "price_to_book": 0.37, "market_cap": 3.99e11},
    {"symbol": "PGSUS", "name": "Pegasus", "price_to_book": 0.64, "market_cap": 7.1e10}
  ]
}
```

- `industry` şirketin kendi alt sektörüdür; `group` listenin neyi kapsadığını adlandırır (alt
  sektör ya da `level=sector` ile sektör); `market` yazıldığı gibi gösterilir ("Borsa İstanbul").
- `symbol`'ün kendisini de listeye koyun: onun oranı realmarket'in hesapladığıyla karşılaştırılır
  ve aradaki fark %25'ten fazlaysa kıyas düşürülür; böylece benzer şirketlerin şirketle aynı
  biçimde ölçüldüğü bilinir.
- Oran yoksa `price_to_book` `null`'dır; her şirketin oranını tek bir para birimi tanımıyla
  verin. Bir şirketin pay grupları (`KRDMA`, `KRDMB`), adları yalnızca sondaki "(A)", "(B)" ile
  ayrılıyorsa, en büyük `market_cap` değerine sahip olanla bir kez sayılır.
- Şirket başına isteğe bağlı `currency` ve `financial_currency`: ikisi farklıysa realmarket o
  şirketi dışarıda bırakır; çünkü kaynaklar çoğu zaman bir para birimindeki fiyatı başka bir para
  birimindeki defter değerine böler.

## `GET /news?q=<text>&start=<ISO>&end=<ISO>&limit=<n>[&language=<xx>]` (isteğe bağlı)

Kurumun kendi akışından haberler ve bildirimler (KAP bildirimleri, Foreks, bir haber ajansı);
en yenisi önce. Adaptör haber sunmuyorsa 404. `REALMARKET_NEWS_PROVIDER=http` olduğunda
kullanılır.

```json
{"articles": [
  {"published_at": "2026-09-20T07:30:00Z", "title": "THYAO: Özel durum açıklaması",
   "url": "https://www.kap.org.tr/tr/Bildirim/123456", "source": "KAP", "language": "tr",
   "country": "TR"}
]}
```

- `published_at` UTC cinsinden, `YYYY-MM-DDTHH:MM:SSZ` biçimindedir; `start`..`end` aralığı
  dışındaki haberler düşürülür.
- `title` ve `http(s)` ile başlayan bir `url` zorunludur; `source` yayıncıyı ya da akışı
  adlandırır.
- Başlıklar modele veri olarak gösterilir, asla talimat olarak değil.

## Fonlar

Yatırım fonları adaptör için sıradan varlıklardır: onları `/search` içinde `asset_class`
`fund` ile listeleyin ve günlük pay fiyatlarını `/bars` üzerinden sunun (`adjustment` `none`;
fon fiyatları dağıtımları zaten içerir). Bu durumda getiri, enflasyon ve birikim araçlarının
hepsi fonlar için de çalışır.

## Adaptörü test etme

realmarket'i bağlamadan önce test aracını adaptöre karşı çalıştırın. Araç her ucu, realmarket'in
çalışırken kullandığı kodla çağırır; bu yüzden aynı nedenlerle geçer ya da kalır:

```bash
REALMARKET_HTTP_TOKEN=... realmarket-adapter-check --url https://marketdata.internal/realmarket/v1 --symbol THYAO
```

```
[PASS] /meta: source adapter:acme-feed
[PASS] /search: 2 result(s) for 'THYAO'
[PASS] /bars: 285 bars for THYAO in TRY, split_and_dividend
[PASS] /bars exchange rate: USDTRY
[PASS] /bars gold: XAUUSD
[PASS] /bars benchmark: XU100
[PASS] price summary: total_return 0.292003
[PASS] /financials: 5 quarters, 3 years
[SKIP] /news: The data adapter does not serve news.

The adapter is ready to connect.
```

Zorunlu: `/meta`, `/search`, `/bars`. Eksik bir döviz kuru, altın ya da gösterge endeks serisi
uyarıdır: ona ihtiyaç duyan kıyaslar atlanır. `/meta` içinde bildirilip sunulmayan isteğe bağlı
bir uç kalır (araçları sunulur ve hata verir); sunulup bildirilmeyen bir uç uyarıdır (araçları
sunulmaz). Zorunlu bir kontrol kaldığında çıkış kodu 1'dir.

## Elle deneme

```bash
python examples/adapter/serve_files.py --root tests/fixtures/basic --port 8765   # or your adapter
REALMARKET_PRICE_PROVIDER=http REALMARKET_HTTP_URL=http://127.0.0.1:8765 realmarket-mcp
```

Ardından istemciden birkaç sembol için `check_data_quality` ve `get_price_summary`
çalıştırmasını isteyin (`check_setup` adaptörle sunulmaz: kişisel kurulumu çalıştıran kişi
içindir). Bu sözleşmeye uymayan bir cevap, ucu ve sorunu adlandıran bir hata üretir.
