# Luckypari VIP Signal Bot

Aiogram 3.22 asosidagi Telegram bot: kanal obunasini tekshirish, Player ID arizasi,
admin tasdiqlashi, SQLite, VIP signallar va APK yuborish.

## Ishga tushirish

1. Python 3.11+ o'rnating va `pip install -r requirements.txt` bajaring.
2. `.env.example` dagi qiymatlarni Railway Variables bo'limiga kiriting (lokalda esa
   tizim environment variable sifatida belgilang).
3. Botni kanalga administrator qiling. `CHANNEL_ID` `-100...` ko'rinishida bo'ladi.
4. APK kerak bo'lsa `assets/luckypari.apk` faylini joylang.
5. `python bot.py` bilan ishga tushiring.

## Railway

GitHub repositoryni Railway'ga ulang, Variables bo'limiga barcha sirlarni kiriting.
`Procfile` worker jarayonini avtomatik boshlaydi. SQLite fayli redeploylarda saqlanishi
uchun Railway Volume ulang va `DATABASE_PATH=/data/bot.db` qilib qo'ying.

## Admin buyruqlari

- `/admin` — panel
- `/pending` — kutilayotgan arizalar
- `/stats` — foydalanuvchi statistikasi

Signal generatori tasodifiy ko'ngilochar taxmin beradi va yutuqni kafolatlamaydi.
