# Kalibrasyon doğrulaması — 29 Eylül 2026

38 birim testi geçti; bunların 11'i yeni kalibrasyon davranışını sınar. Bilinen J123 değerini geri bulma, hata büyüklüğüne göre ağırlıklandırma, doğrulama verisinin optimizasyondan ayrı tutulması, belirlenemeyen parametrelerin işaretlenmesi, koşul/birim/girdi kontrolleri ve sürüm geçmişi test edildi.

Teslim notebook'u üç taze Jupyter çekirdeğinde doğrulandı: boş girdi, sentetik pipeline+kalibrasyon ve tasarım hücreleri çalıştırılmadan yalnız kaydedilmiş variant/baseline ile kalibrasyon. Üçü geçti. Dosya hash'i results.json içinde.

Grafik ve parametre geri-kazanımı sentetik yazılım testidir. Gerçek deney verisiyle model kalibrasyonu veya biyolojik doğrulama yapılmadı. Test verileri teslim notebook'una varsayılan veri olarak konulmadı. GPU tasarım aşamaları bu doğrulamada çalıştırılmadı.
