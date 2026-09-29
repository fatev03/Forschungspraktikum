# Doğrulama kaydı — 29 Eylül 2026

Teslim notebook: `diffusion_trivalent_colab_2026-09-29.ipynb`.
27 birim testi geçti. Notebook iki taze Jupyter çekirdeğinde baştan sona çalıştırıldı: boş girdiler güvenli biçimde durduruldu; sentetik import çalışması her iki bağlantıyı, dört tahmin dosyası alımını, AlphaFold/Boltz dışa aktarımını, AF3-ReD envanterini, polimer senaryosunu, termodinamik grafiği ve ZIP üretimini tamamladı.

Sentetik doğrudan füzyon kompleksindeki reseptör–reseptör çakışmaları doğru biçimde `REVIEW_REQUIRED` olarak raporlandı. Sentetik girdiler gerçeğe uygun protein yapıları veya deneysel ölçümler değildir. Test sonuçları biyolojik doğrulama sayılmaz; notebook'a varsayılan veri olarak yerleştirilmedi.

`results.json` teslim notebook hash'ini ve yürütme durumlarını içerir. `*.executed.ipynb` doğrulama kopyalarıdır; Colab'e yüklemek için üst dizindeki teslim notebook'u kullan. Grafik koşullu bir yazılım test senaryosudur, gerçek reseptör tahmini değildir.

GPU kurulumu/çıkarımı, gerçek hedefler ve PyMOL uygulamasında görsel inceleme çalıştırılmadı. PyMOL betiğinin çağrıları sahte komut arayüzüyle doğrulandı. Eski kullanıcı notebook'ları korunmuştur.
