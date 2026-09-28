# Aracı kurumlar için entegrasyon rehberi

Bu rehber, realmarket'i kendi mobil uygulamasındaki yapay zekâ asistanına bağlamak isteyen
aracı kurumun ürün, BT ve veri ekipleri içindir. Teknik ayrıntının tamamı
[`adapter-api.md`](adapter-api.md) (veri servisi sözleşmesi) ve
[`integration.md`](integration.md) (sunucu, model, denetim kaydı) belgelerindedir.

## Ne işe yarar

Müşteri uygulamadaki asistana "Portföyüm nasıl?", "THYAO enflasyonu yendi mi?", "EREGL ucuz
mu?" gibi sorular sorar. Asistan cevabı kendi bilgisinden değil, realmarket'in hesapladığı
rakamlardan kurar:

- getiriler, enflasyona göre reel getiri, dolar, altın, mevduat, konut ve asgari ücrete göre
  kıyaslar, gerçek alım satımlardan portföy analizi (bedelsiz ve temettü dahil), değerleme
  oranları ve sektör kıyası, finansal tablolar (TMS 29 dahil), olay tepkileri;
- her rakamın kaynağı, dönemi ve veri sürümü; veri kalitesi uyarıları;
- Türkçe olgu cümleleri: her rakam anlamı ve tarihiyle gelir, model onu aktarır.

Araçlar al, sat, tut önerisi, hedef fiyat, fiyat hareketine neden ya da "ucuz/pahalı" hükmü
üretmez. 119 gerçek müşteri sorusunda en küçük model (Claude Haiku) %96, Claude Sonnet %100
doğru cevap verdi; hiçbir cevapta tavsiye ya da neden uydurma yoktu
(`evals/reports/2026-09-28-full-run-2.md`).

## Mimari

```
Müşteri → kurumun uygulaması → kurumun yapay zekâ modeli → realmarket (MCP sunucusu)
                                                               │
                         ┌─────────────────────────────────────┼─────────────────────┐
                 kurumun veri servisi (adaptör)          TCMB EVDS            haberler (isteğe bağlı)
                 lisanslı fiyat, temettü, bedelsiz,      enflasyon, mevduat,  kurumun KAP/haber akışı
                 finansallar, sektör listesi             konut fiyatları      ya da GDELT
```

- Veri kurumun ağından çıkmaz: realmarket veriyi saklamaz, her soruda adaptörden okur.
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
| `/peers` | Hayır | "Ucuz mu?" sorusunun cevabı olan sektör kıyası |
| `/news` | Hayır | KAP bildirimleri ve haberler |

Başlangıç noktası: `examples/adapter/serve_files.py` (yalnızca standart kütüphane; dosyadan
okuyan kısımları kendi kaynağınıza yönlendirirsiniz).

### 2. Adaptörü test edin

```bash
REALMARKET_HTTP_TOKEN=... realmarket-adapter-check --url https://veri.kurum.internal/realmarket/v1 --symbol THYAO
```

Her uç için GEÇTİ / UYARI / KALDI / ATLANDI raporu verir; atlanan isteğe bağlı bir parça,
hangi özelliğin çalışmayacağını söyler. Test aracı, realmarket'in çalışırken kullandığı kodla
aynı kodu kullanır: burada geçen üretimde de çalışır.

### 3. realmarket'i çalıştırın

```bash
REALMARKET_PRICE_PROVIDER=http \
REALMARKET_HTTP_URL=https://veri.kurum.internal/realmarket/v1 \
REALMARKET_HTTP_TOKEN=... \
REALMARKET_EVDS_API_KEY=... \
realmarket-mcp --transport http --host 127.0.0.1 --port 8000
```

- `REALMARKET_EVDS_API_KEY`: TCMB EVDS anahtarı (enflasyon, mevduat, konut); ücretsiz alınır.
- `REALMARKET_NEWS_PROVIDER=http`: haberleri kendi adaptörünüzden almak için.
- `REALMARKET_AUDIT_LOG`: her araç çağrısının denetim kaydı (bkz. `integration.md`).
- Anahtarlar yalnızca ortam ayarlarında durur; hiçbir cevapta ya da kayıtta yazılmaz.

### 4. Modeli bağlayın ve sınayın

Modelinizi MCP istemcisiyle `http://127.0.0.1:8000/mcp` adresine bağlayın. Sunucu, kullanım
talimatlarını bağlantı sırasında gönderir; bunları modelin bağlamında tutun. Canlıya
almadan önce modelinizi sınayın:

```bash
realmarket-qualify --base-url <modelinizin OpenAI uyumlu adresi> --model <model> --output rapor.json
```

## Güvenlik

- realmarket'in MCP ucunun kendi kimlik doğrulaması yoktur: iç ağda tutun ve kurumun API
  geçidinin arkasına koyun.
- Adaptöre giden anahtar yalnızca `Authorization` başlığında gönderilir, yönlendirmelerde
  aktarılmaz, kaydedilmez.
- Adaptörden gelen her cevap sıkı doğrulanır; bozuk veri onarılmaz, uç ve sorun adıyla hataya
  döner.
- Haber başlıkları modele talimat olarak değil, veri olarak verilir.

## Tahmini iş yükü

| İş | Kim | Tahmini süre |
|---|---|---|
| Zorunlu üç uç (`/meta`, `/search`, `/bars`) | Kurumun bir geliştiricisi | Birkaç gün |
| Temettü, bedelsiz, finansallar, sektör listesi | Aynı geliştirici | Bir hafta civarı, verinin hazırlığına bağlı |
| Sunucu kurulumu, API geçidi, izleme | BT | Birkaç gün |
| Modelin sınanması ve uygulamaya bağlanması | Ürün ve BT | Bir-iki hafta |

Süreler kaba tahmindir; kurumun veri kaynağının hazırlığına göre değişir.

## Kurumda kalan sorumluluklar

- Verinin lisansı ve doğruluğu (realmarket veriyi denetler ama kaynağın yerine geçmez).
- Modelin seçimi ve sınanması; müşteriye gösterilen metin ve uyarılar.
- SPK mevzuatı açısından değerlendirme: araçlar tavsiye üretmez, ancak ürünün mevzuata
  uygunluğu kurumun hukuk ve uyum birimlerinin kararıdır.
