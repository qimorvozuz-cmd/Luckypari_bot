import random
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Signal:
    game: str
    prediction: str
    mode: str


def apple_signal() -> Signal:
    return Signal("Apple", f"{random.choice([2, 3, 4])} ta olma — keyin chiqish", "VIP")


def chicken_signal() -> Signal:
    return Signal("Chicken Road", f"{random.uniform(1.20, 2.50):.2f}x da chiqish", "VIP")


def mines_signal() -> Signal:
    cells = sorted(random.sample(range(1, 26), 4))
    return Signal("Mines", "Xavfsiz katak taxmini: " + ", ".join(map(str, cells)), "VIP")


def aviator_signal() -> Signal:
    return Signal("Aviator", f"Ehtiyotkor chiqish nuqtasi: {random.uniform(1.25, 2.20):.2f}x", "VIP")


def luckyjet_signal() -> Signal:
    return Signal("Lucky Jet", f"Taxminiy chiqish: {random.uniform(1.20, 2.00):.2f}x", "VIP")


def format_signal(signal: Signal) -> str:
    signal_id = datetime.now().strftime("%H%M%S") + str(random.randint(10, 99))
    return (
        "✨ <b>VIP SIGNAL TAYYOR</b> ✨\n\n"
        f"🎮 O'yin: <b>{signal.game}</b>\n📍 Tavsiya: <b>{signal.prediction}</b>\n"
        f"🆔 Signal: <code>#{signal_id}</code>\n🔐 Rejim: {signal.mode}\n\n"
        "⚠️ Bu avtomatik ko'ngilochar taxmin. Natija va yutuq kafolatlanmaydi."
    )
