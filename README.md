# Luckypari PRO VIP / MEGA VIP Bot

Aiogram 3.22 va SQLite asosidagi ikki darajali Telegram bot.

## Foydalanuvchi imkoniyatlari

- Maxfiy kanalga majburiy obuna va qayta tekshirish
- VIP (50 000 so'm) va MEGA VIP (100 000 so'm) arizalari
- Player ID orqali admin tasdig'i
- Apple, Chicken Road, Mines, Aviator va Lucky Jet animatsiyali taxminlari
- Admin joylaydigan kunlik stavkalar
- MEGA VIP uchun yuqori koeffitsiyent, casino tahlillari va hisobotlar
- Darajaga mos konkurs, promo, FreeBet va bonuslar
- Shaxsiy kabinet va APK
- Shaxsiy referral havola; tasdiqlangan referral uchun 10 000 so'm ichki bonus
- Yordam xabarini adminga forward qilish va admin javobi

## Admin panel

Admin `/start` qilganda pastda doimiy `🛠 Admin panel` tugmasi chiqadi.

- Ikonli arizalar jadvali va tasdiqlash/rad etish
- Foydalanuvchini ID orqali tekshirish, VIP/MEGA darajasi, bloklash va alohida xabar
- Barcha/VIP/MEGA/tanlangan auditoriyaga xabar va reklama
- Promo, FreeBet, konkurs, kunlik stavka va MEGA kontentini boshqarish
- Qo'shimcha kanal yoki guruhga qo'shilish taklifi
- Kanal obunalarini ommaviy tekshirish va obuna bo'lmaganlarni ogohlantirish
- Referral bonus to'lov navbati
- APK yuklash va barcha tasdiqlanganlarga tarqatish
- Statistika

## Railway Variables

`.env.example` dagi nomlar bilan quyidagi qiymatlarni kiriting:

```env
BOT_TOKEN=BotFather_tokeni
ADMIN_IDS=123456789
CHANNEL_ID=-1001234567890
CHANNEL_URL=https://t.me/+maxfiy_taklif_havolasi
REGISTRATION_URL=https://affiliate-havolangiz
PROMO_CODE=XXXX
VIP_DEPOSIT=50000
MEGA_DEPOSIT=100000
REFERRAL_REWARD=10000
APK_PATH=/data/luckypari.apk
DATABASE_PATH=/data/bot.db
```

Railway Volume aynan `/data` manziliga ulanishi kerak. `/app` ga Volume ulamang,
aks holda dastur fayllari yopilib qoladi. `Procfile` botni `python bot.py` bilan ishga tushiradi.

## Muhim

Depozitni va referral bonusini real Luckypari hisobiga avtomatik o'tkazish faqat rasmiy
Luckypari API bilan mumkin. Ushbu versiyada admin Player ID orqali tekshiradi; referral
bonusi ichki balans va to'lov navbatida yuritiladi, to'langach admin belgilaydi.

Casino signallari ko'ngilochar avtomatik taxmin bo'lib, natija yoki yutuqni kafolatlamaydi.
Kunlik stavka va MEGA kontentini admin panel orqali administrator joylaydi.
