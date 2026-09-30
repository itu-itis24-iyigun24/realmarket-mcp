# realmarket-mcp

Claude'un ve diğer büyük dil modellerinin (LLM) piyasaları **doğrulanmış ve kaynağı belli
rakamlarla** araştırmasını sağlayan açık kaynak bir
[Model Context Protocol](https://modelcontextprotocol.io) sunucusu.

> **Durum: alfa (MVP).** Fiyat, reel getiri, veri kalitesi ve ABD finansal tablo araçları canlı
> Yahoo, SEC EDGAR, OECD, FRED, TCMB EVDS ve GDELT servislerine karşı doğrulandı. KAP şirket
> bildirimleri dahil değildir (KAP'ın kullanım koşulları MKK'nın yazılı iznini şart koşar);
> bunlar için [kapmcp](#kapmcp-ile-birlikte-kullanmak-kap-bildirimleri-ve-finansal-tablolar) ile
> birlikte kullanın.

## Neden

Bir dil modeline bir varlığın nasıl performans gösterdiğini sorduğunuzda çoğu zaman ezberden ya
da tahminle cevap verir. Yüksek enflasyonlu bir para biriminde birikim yapan biri için sonraki
soruyu, yani *gerçekten enflasyonu yendi mi?* sorusunu güvenilir biçimde cevaplamak daha da
zordur. realmarket-mcp modele bu rakamları kodla hesaplayan ve kaynaklarıyla birlikte döndüren
araçlar verir:

- **Reel getiri**: nominal getiri ile varlığın kendi para birimindeki enflasyonun kıyası; aynı
  getirinin ABD doları ve altın cinsinden ölçümü.
- **Veri kalitesi kontrolleri**: boşluklar, bölünme ve sıfır atma (redenominasyon) kaynaklı
  kopukluklar, yer tutucu barlar. Bunlar etkiledikleri rakamların yanında işaretlenir, hiçbir
  zaman sessizce "düzeltilmez".
- **Her rakamda kaynak bilgisi**: sağlayıcı, dönem, verinin alındığı zaman ve kullanılan verinin
  tam içerik özeti (hash).
- **Deterministik sonuçlar**: aynı veri ve aynı argümanlar, soran model hangisi olursa olsun aynı
  cevabı verir.

## Araçlar

| Araç | Neyi cevaplar |
|---|---|
| `search_assets` | "Türk Hava Yolları'nın sembolü ne?" |
| `get_price_summary` | "Son bir yılda nasıl gitti?": getiri, yıllıklandırılmış getiri, oynaklık, en büyük düşüş, getirinin ne kadarının temettüden geldiği ve son dönem temettü verimi |
| `compare_real_return` | "Enflasyonu yendi mi?": nominal ve reel getiri; aynı yatırımın ABD doları, altın (ve TL cinsinden gram altın) ve asgari ücret cinsinden karşılığı; TL varlıklar için stopaj öncesi ve sonrası TL mevduatla ve konut fiyatlarıyla kıyas |
| `compare_assets` | "Bunlar birbirine göre nasıl?": ortak bir dönemde 2 ile 10 arası varlık |
| `check_data_quality` | "Bu veriye güvenebilir miyim?": boşluklar, yer tutucu barlar, şüpheli sıçramalar, güncel olmayan veri |
| `explain_price_move` | "Bugün neden düştü?": seansın etrafındaki olgular: hissenin hareketi ile endeksin hareketi yan yana, hareketin ve işlem hacminin ne kadar olağandışı olduğu, temettü dağıtım (hak kullanım) günleri ve o günün haberleri ya da bildirimleri; bir neden göstermeden |
| `analyze_portfolio` | "Portföyüm nasıl gidiyor?": hesabın alımları, satımları, temettüleri ve bedelsizlerinden her varlığın maliyeti, değeri, ağırlığı, gerçekleşmiş ve gerçekleşmemiş kârı; toplamlar, para ağırlıklı getiri, yoğunlaşma, en iyi ve en kötü varlık, son bir yılın oynaklığı ve en büyük düşüşü |
| `portfolio_real_return` | "Birikimim enflasyona yetişti mi?": tarihli alımların bugünkü değeri, para ağırlıklı getiri, reel getiri ve aynı ödemelerin USD, altın, TL mevduat (stopaj sonrası dahil), konut ya da bir endekse yatırılmış olsaydı ne olacağı |
| `get_event_reaction` | "Hisse o açıklamaya nasıl tepki verdi?": endekse göre 1/5/20 seanslık getiri ve olaydan önceki seyir |
| `get_financials` | "Son çeyrek nasıl geçti?": reel olarak hasılat, kâr, marjlar, borçluluk ve büyüme; ABD şirketleri resmî SEC başvurularından, Türkiye'deki enflasyon muhasebesi (TMS 29) hesaba katılarak, veri hataları işaretlenerek |
| `get_valuation` | "Kazancına göre pahalı mı fiyatlanıyor?": piyasa değeri, F/K, PD/DD ve F/S; kur çevrimi ve Türkiye'deki enflasyon muhasebesi hesaba katılarak |
| `find_official_filer` | "ASML'nin resmî raporlarındaki kimliği ne?": ESEF yıllık rapor dizinindeki Avrupa ve Birleşik Krallık şirketleri, LEI kodlarıyla |
| `check_setup` | "Her şey ayarlı mı?": hangi veri kaynaklarının açık olduğu ve hangi ayarların eksik olduğu |
| `get_news` | "Onunla ilgili haberlerde ne vardı?": yayıncı, tarih ve bağlantıyla son haber listesi |

Sunucu ayrıca üç rapor istemi (`single_asset_report`, `real_return_report`,
`comparison_report`) ve tüm formülleri içeren bir `realmarket://methodology` kaynağı sunar.

## Kurulum

### Claude eklentisi olarak (Claude Code ve Cowork)

Sunucuyu ayrı bir Python kurulumu olmadan çalıştıran
[uv](https://docs.astral.sh/uv/getting-started/installation/) gerekir.

```bash
claude plugin marketplace add itu-itis24-iyigun24/realmarket-mcp
claude plugin install realmarket@realmarket
```

Ardından ayarları doldurmak için `/plugin configure realmarket@realmarket` komutunu çalıştırın
(ya da kurulum komutuna `--config KEY=VALUE` verin). Hepsi isteğe bağlıdır:

| Ayar | Ne yapar |
|---|---|
| `use_yahoo` | İşaretlenirse Yahoo Finance'ten fiyatlar, döviz, altın ve ABD dışı finansal tablolar gelir (resmî değil; aşağıya bakın). Varsayılan olarak kapalı. |
| `sec_contact` | ABD şirketlerinin resmî SEC finansal tabloları için e-posta adresiniz |
| `evds_api_key` | En güncel Türkiye TÜFE'si (TCMB EVDS); maskeli saklanır |
| `fred_api_key` | FRED API üzerinden ABD TÜFE'si; maskeli saklanır, gerekli değildir |

Eklenti ayrıca Claude'a araçları nasıl kullanacağını ve kaynaklarını nasıl bildireceğini anlatan
bir `market-research` becerisi (skill) ekler.

### Claude Desktop uzantısı olarak (.mcpb)

1. `realmarket-<version>.mcpb` dosyasını
   [son sürümden](https://github.com/itu-itis24-iyigun24/realmarket-mcp/releases/latest) indirin.
2. Claude Desktop'ta **Settings → Extensions → Advanced settings → Install Extension…** yolunu
   açın ve indirdiğiniz dosyayı seçin.
3. Yukarıdaki ayarların aynısını doldurun (fiyatlar için **Use Yahoo Finance** kutusunu
   işaretleyin), sonra Claude Desktop'tan tamamen çıkın (yalnızca pencereyi kapatmak yetmez;
   sistem tepsisinden / menü çubuğundan çıkın) ve yeniden açın.

Claude Desktop Python bağımlılıklarını uv ile kendisi kurar; sürümleri paketin `uv.lock`
dosyası sabitler. Python kurulumu gerekmez. Dosyayı kaynak koddan derlemek için:

```bash
python scripts/build_mcpb.py
npx -y @anthropic-ai/mcpb validate build/mcpb/manifest.json
npx -y @anthropic-ai/mcpb pack build/mcpb dist/realmarket-<version>.mcpb
```

### Sorun giderme

- **Claude'dan `check_setup` aracını çalıştırmasını isteyin.** Sunucunun hangi kaynakları
  kullanacağını ve hangi ayarların eksik olduğunu, hiçbir değeri göstermeden listeler.
- **Uzantının yeni bir sürümünü kurduktan sonra** ayarlarını açıp kontrol edin: Claude Desktop
  önceki değerleri taşımayabilir (örneğin **Use Yahoo Finance** yeniden işaretsiz olabilir).
- **Bir ayarı değiştirdikten sonra "No price data source is configured" hatası:** ayarlar
  sunucuya yalnızca sunucu başlarken ulaşır. Uygulamadan tamamen çıkın (Windows'ta sistem
  tepsisi, macOS'ta menü çubuğu), yeniden açın ve yeni bir sohbet başlatın.
- **Türkiye reel getirileri daha eski bir ayda kalıyor:** TCMB EVDS anahtarı yoksa Türkiye
  enflasyonu OECD'den gelir ve OECD, TÜİK'in yayımlarının gerisinden gelir. Anahtarı ayarlara
  ekleyin.
- **Hâlâ çalışmıyorsa:** sunucu kaydı Windows'ta `%APPDATA%\Claude\logs`, macOS'ta
  `~/Library/Logs/Claude` klasöründe, adında `realmarket` geçen dosyadadır. Bir issue'da
  paylaşmadan önce içindeki API anahtarlarını ve e-posta adreslerini silin.

### Sade bir MCP sunucusu olarak (her MCP istemcisi)

Python 3.11+ gerekir.

```bash
pip install "realmarket-mcp[yahoo] @ git+https://github.com/itu-itis24-iyigun24/realmarket-mcp"
```

## İstemciyi yapılandırma

Tüm yapılandırma, istemcinin MCP sunucu tanımındaki ortam değişkenleriyle yapılır. Claude
Desktop (`claude_desktop_config.json`) ya da aynı biçimi kullanan herhangi bir istemci için
örnek:

```json
{
  "mcpServers": {
    "realmarket": {
      "command": "realmarket-mcp",
      "env": {
        "REALMARKET_PRICE_PROVIDER": "yahoo",
        "REALMARKET_SEC_CONTACT": "you@example.com",
        "REALMARKET_EVDS_API_KEY": "your-tcmb-evds-key",
        "REALMARKET_FRED_API_KEY": "your-fred-key"
      }
    }
  }
}
```

Claude Code için: `claude mcp add realmarket -e REALMARKET_PRICE_PROVIDER=yahoo -- realmarket-mcp`.

| Değişken | Amaç |
|---|---|
| `REALMARKET_PRICE_PROVIDER` | `yahoo`, `http` (kendi veri servisiniz (adaptör); aşağıya bakın) ya da çevrimdışı test verisi için `fixture` |
| `REALMARKET_HTTP_URL`, `REALMARKET_HTTP_TOKEN` | Adaptörünüzün temel adresi ve isteğe bağlı bearer anahtarı |
| `REALMARKET_USE_YAHOO` | `REALMARKET_PRICE_PROVIDER` ayarlanmamışsa `true` Yahoo'yu açar (eklentideki ve uzantıdaki onay kutusu budur) |
| `REALMARKET_SEC_CONTACT` | *İsteğe bağlı.* E-posta adresiniz; SEC bunu her otomatik istekte ister. Bu ayar varsa ABD şirketlerinin finansal tabloları resmî SEC başvurularından gelir (anahtar ya da üyelik gerekmez) |
| `REALMARKET_FINANCIALS_PROVIDER` | `auto` (varsayılan: iletişim adresi ayarlıysa ABD sembolleri için SEC, değilse fiyat sağlayıcısı), `sec` ya da `price` |
| `REALMARKET_EVDS_API_KEY` | *İsteğe bağlı.* TCMB EVDS'den Türkiye TÜFE'si; en güncel kaynak (ücretsiz anahtar: evds3.tcmb.gov.tr) |
| `REALMARKET_FRED_API_KEY` | *İsteğe bağlı.* FRED API üzerinden ABD TÜFE'si (ücretsiz anahtar: fred.stlouisfed.org) |
| `REALMARKET_CPI_CSV_<REGION>` | Herhangi bir bölge için kendi aylık TÜFE dosyanız (`month,cpi_index`), ör. `REALMARKET_CPI_CSV_TR` |
| `REALMARKET_NEWS_PROVIDER` | `gdelt` (varsayılan, ücretsiz, anahtarsız), `http` (adaptörün haberleri; adaptörle çalışırken varsayılan) ya da `none` |
| `REALMARKET_SERVER_TOKEN` | Yalnızca HTTP taşıması için: her isteğin taşıması gereken bearer anahtarı (en az 32 karakter); 127.0.0.1 dışındaki bir adreste hizmet vermek için zorunludur |
| `REALMARKET_FOREIGN_SOURCES` | `on`/`off`: yurt dışındaki anahtarsız kaynakların (enflasyon için OECD ve FRED'in herkese açık CSV'si, ESEF, GDELT) ayarlanmadan kullanılıp kullanılmayacağı. Varsayılan olarak açık; **adaptörle çalışırken varsayılan olarak kapalı**, böylece bir kurumun kurulumu yalnızca kendi adaptörüne ve kendi ayarladığı kaynaklara bağlanır |
| `REALMARKET_FIXTURE_DIR` | `fixture` sağlayıcısının klasörü |

**Hiçbir anahtar zorunlu değildir.** Anahtar olmadan enflasyon OECD'nin herkese açık API'sinden
gelir (ABD, Türkiye ve diğer OECD üyeleri); ABD için yedek kaynak FRED'in herkese açık CSV'sidir.
OECD'nin Türkiye serisi şu anda 2025-12'de bitiyor; bu yüzden EVDS anahtarı olmadan Türkiye reel
getirileri orada durur ve bunu belirtir. Güncel veri için EVDS anahtarını ayarlayın.

### Yahoo Finance sağlayıcısı hakkında

`yahoo`, Yahoo Finance'in herkese açık web uçlarını okuyan topluluk kütüphanesi
[`yfinance`](https://github.com/ranaroussi/yfinance)'i kullanır. Bu **resmî bir API değildir** ve
**Yahoo'nun Hizmet Koşulları, Yahoo'nun açık ve önceden verilmiş izni olmadan, hangi amaçla
olursa olsun, hizmetlerine otomatik yollarla erişilmesini ya da hizmetlerinden otomatik yollarla
veri toplanmasını yasaklar**; koşullarda kişisel kullanım için bir istisna yoktur. Uçlar da
haber verilmeden değişir ve bazı fiyat geçmişlerinde hatalar vardır (`check_data_quality` bu
yüzden var). realmarket-mcp'nin Yahoo ile bir bağlantısı yoktur ve Yahoo tarafından
desteklenmez; Yahoo, sahibinin ticari markasıdır. Sağlayıcı siz seçmedikçe kapalıdır; seçerek
Yahoo'nun koşulları kapsamındaki kullanımınızın sorumluluğunu üstlenirsiniz ve veriyi yeniden
dağıtamazsınız. Veri gecikmeli ya da hatalı olabilir, arayüz haber verilmeden bozulabilir.
Semboller Yahoo'nun yazımını izler: `THYAO.IS` (Borsa İstanbul), `XU100.IS`, `USDTRY=X`,
`GC=F` (altın).

### Finansal tablo kaynakları

| Piyasa | Kaynak | Resmî mi |
|---|---|---|
| US GAAP ile raporlayan ABD'de işlem gören şirketler (10-Q / 10-K ve ASML gibi 20-F verenler) | SEC EDGAR XBRL API, `REALMARKET_SEC_CONTACT` ile | evet |
| Avrupa ve Birleşik Krallık'ta işlem gören şirketler (ESEF, UFRS), LEI ile; Almanya ve İrlanda hariç | filings.xbrl.org, ayar gerekmez | evet |
| Diğer her şey, Borsa İstanbul dahil | Yahoo Finance (`REALMARKET_PRICE_PROVIDER=yahoo`) | hayır; şirketin resmî raporlarından doğrulayın (Borsa İstanbul için KAP) |

ABD sembolleri Yahoo'nun yazımını kullanır (`AAPL`, `BRK-B`); `CIK0000320193` gibi bir CIK de
çalışır. Bir Avrupa şirketi için `find_official_filer` adayları LEI kodlarıyla döndürür; LEI'yi
sembol olarak verdiğinizde şirketin resmî ESEF raporlarından, UFRS'ye göre yıllık (şirket
oraya çeyreklik rapor da veriyorsa çeyreklik) rakamlar gelir. Bunlar aynı şirketin SEC'e US GAAP
ile bildirdiklerinden farklı olabilir. filings.xbrl.org Alman ve İrlandalı şirketlerin
raporlarını tutmaz. SEC'te bir şirketin tabloları yoksa (TSM gibi UFRS ile raporlayanlar) ya da
SEC sembolü listelemiyorsa fiyat sağlayıcısının tabloları kullanılır ve sonucun kaynak bilgisi
kaynağı belirtir. Dördüncü çeyrek gelir tablosu rakamları, şirketler bunları ayrıca
yayımlamadığı için yıllıktan dokuz aylık çıkarılarak türetilir; sonuç hangi çeyreklerin
türetildiğini listeler. SEC verisi kamuya açıktır; SEC otomatik istemcilerden saniyede 10
isteğin altında kalmalarını ve kendilerini tanıtmalarını ister.

### TÜFE kaynakları

| Bölge | Anahtarsız | Anahtarla |
|---|---|---|
| Türkiye | OECD (TÜİK ile aynı; şu anda 2025-12'de bitiyor) | TCMB EVDS (güncel) |
| Amerika Birleşik Devletleri | OECD (güncel; yedek olarak FRED'in herkese açık CSV'si) | FRED API (aynı BLS verisi) |
| Diğer OECD üyeleri (ör. DE, GB) | OECD (yayımlandığı yerde güncel) | — |
| Diğer her yer | `REALMARKET_CPI_CSV_<REGION>` | — |

OECD'nin herkese açık API'si saatte yaklaşık 60 indirmeye izin verir; bu yüzden her seri bir kez
indirilir ve altı saat boyunca yeniden kullanılır. Sonuçlar ilk alınma zamanını korur.

### TL mevduat kıyası

TCMB EVDS anahtarı varsa TL sonuçları aynı paranın mevduatta ne kazandıracağını da gösterir:
TCMB'nin 1-3 ay vadeli yeni TL mevduatlar için yayımladığı haftalık ağırlıklı ortalama faizle
her vade sonunda yenilenen 32 günlük mevduat (EVDS `TP.TRYTAS.MT02`; Temmuz 2012'den önce tüm TL
mevduatlar, `TP.TRY.MT02`). Rakamlar **stopaj öncesi brüt** rakamlardır; gerçek bir hesap kendi
bankasının faizini kazanır.

### Kendi veriniz, kendi modeliniz

Lisanslı piyasa verisi olan kurumlar bu veriyi küçük bir HTTP **adaptörü** üzerinden bağlayabilir
([`docs/adapter-api.md`](docs/adapter-api.md); çalışan bir örnek `examples/adapter/` altında) ve
realmarket'i `realmarket-mcp --transport http` ile merkezî olarak kendi yapay zekâ asistanları
için çalıştırabilir. Model yalnızca Claude olmak zorunda değildir; tool calling destekleyen her
model olur. Denetim kaydı her araç çağrısını arkasındaki verinin tam haliyle kaydeder
(`REALMARKET_AUDIT_LOG`); `realmarket-qualify` da bir modelin müşterilere cevap vermeden önce
araçları doğru kullandığını sınar. Bkz. [`docs/entegrasyon-rehberi.md`](docs/entegrasyon-rehberi.md).

## Veri kaynakları, kullanım koşulları ve gizlilik

realmarket-mcp hiçbir veriyle birlikte gelmez. Veriyi sizin adınıza aşağıdaki servislerden çeker
ve **kullanarak açtığınız her servisin koşullarını kabul etmiş olursunuz**. Her sonucun kaynak
bilgisi, kaynağının istediği atfı taşır.

| Servis | Ne için kullanılır | Koşullar (özet) | Gizlilik |
|---|---|---|---|
| SEC EDGAR | ABD finansal tabloları | Kamuya açık veri; kendinizi tanıtın (iletişim e-postası), saniyede en fazla 10 istek | [politika](https://www.sec.gov/about/privacy-information); e-posta adresinizi alır |
| TCMB EVDS | Türkiye TÜFE'si ve TL mevduat faizleri (anahtarla) | Kaynak gösterilerek kullanılabilir ve yayımlanabilir; yatırım tavsiyesi değildir; kullanıcılardan bunun için ücret alınamaz | [politika](https://evds3.tcmb.gov.tr/igmevdsms-dis/documents/showDocument?docId=22) |
| FRED | ABD TÜFE'si (anahtarla API; yedek olarak CSV) | API için [FRED® API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html); CSV için FRED web sitesi koşulları (kişisel, ticari olmayan kullanım) | [politika](https://www.stlouisfed.org/about-us/privacy-policy) |
| OECD | Anahtarsız TÜFE | CC BY 4.0; OECD kaynak gösterilmeli | [politika](https://www.oecd.org/en/about/privacy.html) |
| filings.xbrl.org (XBRL International) | Resmî AB/Birleşik Krallık yıllık raporları | Ücretsiz; "verinin hangi yollarla kullanılabileceğine dair hiçbir kısıtlama yok" | [politika](https://www.xbrl.org/the-consortium/about/legal/privacy-policy/); yalnızca şirket adlarını ve LEI kodlarını alır |
| GDELT | Haber listeleri | Her türlü kullanım için ücretsiz; GDELT Project bağlantıyla kaynak gösterilmeli | yalnızca arama metnini alır |
| Yahoo Finance (isteğe bağlı, siz açarsanız) | Fiyatlar, döviz, altın, ABD dışı finansal tablolar | Koşullar izinsiz otomatik erişimi yasaklar (yukarıya bakın) | [politika](https://legal.yahoo.com/us/en/yahoo/privacy/index.html) |

**FRED:** FRED API anahtarı ayarlarsanız
[FRED® API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html) koşullarıyla
bağlı olmayı kabul edersiniz. Bu ürün FRED® API'sini kullanır, ancak Federal Reserve Bank of
St. Louis tarafından onaylanmış ya da sertifikalandırılmış değildir. Türkiye TÜFE'sini TÜİK
yayımlar. Ayrıntılar ve her satırın dayanağı: [`docs/providers.md`](docs/providers.md).

## kapmcp ile birlikte kullanmak (KAP bildirimleri ve finansal tablolar)

realmarket-mcp, Türkiye'nin Kamuyu Aydınlatma Platformu KAP'ı okumaz: KAP'ın koşulları otomatik
kullanım için MKK'nın yazılı iznini şart koşar (bkz. [`docs/providers.md`](docs/providers.md)).
Bağımsız açık kaynak proje [kapmcp](https://github.com/hasancagrigungor/kapmcp)
(`pip install kap-mcp-server`) KAP'ı MKK'nın resmî API'si üzerinden kapsar. MCP istemcileri
aynı anda birden çok sunucu çalıştırabildiği için ikisi yan yana kullanılabilir; model araçları
ikisinden de seçer.

| Soru | Hangisi cevaplar |
|---|---|
| Şirket bildirimleri, ekleri, resmî finansal tablolar, sermaye işlemleri | kapmcp |
| Nominal ve enflasyondan arındırılmış getiri; aynı yatırımın ABD doları ve altın cinsinden karşılığı | realmarket-mcp |
| "Bu fiyat geçmişine güvenebilir miyim?" (kopukluklar, boşluklar, yer tutucu barlar) | realmarket-mcp |
| Yayıncı, tarih ve bağlantıyla son haberler | ikisi de (kapmcp Yahoo üzerinden, realmarket-mcp GDELT üzerinden) |

İki sunucuyla örnek yapılandırma:

```json
{
  "mcpServers": {
    "realmarket": {
      "command": "realmarket-mcp",
      "env": {
        "REALMARKET_PRICE_PROVIDER": "yahoo",
        "REALMARKET_EVDS_API_KEY": "your-tcmb-evds-key",
        "REALMARKET_FRED_API_KEY": "your-fred-key"
      }
    },
    "kap": {
      "command": "kapmcp",
      "env": { "KAP_API_KEY": "your-mkk-api-key" }
    }
  }
}
```

İkisini birden kullanan örnek istek: *"THYAO'nun KAP'taki son finansal raporunu özetle, sonra
hissenin son üç yılda Türkiye enflasyonunu yenip yenmediğini dolar ve altın cinsinden de söyle.
Önce veri kalitesi sorunlarını belirt."*

Notlar:

- kapmcp kendi geliştiricisi ve lisansı (MIT) olan ayrı bir projedir; realmarket-mcp'nin onunla
  bir bağlantısı yoktur ve onu denetlememiştir. Güncel kurulum için kendi belgelerine bakın.
- KAP araçları için [MKK API Portal](https://apiportal.mkk.com.tr)'dan bir API anahtarı ve MKK
  tarafında IP yetkilendirmesi gerekir; başvururken MKK'nın koşullarını okuyun. Anahtar olmadan
  da Yahoo tabanlı araçları çalışır.
- İki sunucu benzer araçlar sunduğunda (ikisi de fiyat verebilir) ve cevap önemliyse hangisini
  istediğinizi söyleyin, ör. "reel getiri için realmarket'i kullan".

## Örnek sorular

- "THYAO son 5 yılda Türkiye enflasyonunu yendi mi? Dolar ve altın cinsinden de."
- "BIST 100, altın ve S&P 500'ü son 3 yıl için karşılaştır."
- "ASELS'in 2015'ten bu yana fiyat geçmişi güvenilir mi?"

## Ne değildir

- **Yatırım tavsiyesi değildir.** Ölçer ve kıyaslar; ne alıp ne satacağınızı hiçbir zaman
  söylemez.
- **Bir veri hizmeti değildir.** Hiçbir piyasa verisiyle birlikte gelmez. Sizin makinenizde
  çalışır ve veriyi sağlayıcılardan sizin erişiminizle çeker; her sağlayıcının koşullarından siz
  sorumlusunuz.
- **Bir alım satım botu değildir**, fiyat tahmin aracı da değildir.

## Geliştirme

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
python -m mypy
```

Depo, `.claude/` altında Claude Code geliştirme ajanları, becerileri (skills) ve kancaları
(hooks) içerir; bkz. [`CLAUDE.md`](CLAUDE.md).

## Lisans

[Apache-2.0](LICENSE).
