import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    game: str
    prediction: str


def apple_signal() -> Signal:
    return Signal("Apple", f"{random.choice([2, 3, 4])} ta olma — keyin chiqish")


def chicken_signal() -> Signal:
    return Signal("Chicken Road", f"{random.uniform(1.20, 2.50):.2f}x da chiqish")


def format_signal(signal: Signal) -> str:
    return (f"🎯 <b>{signal.game} signali</b>\n\n{signal.prediction}\n\n"
            "⚠️ Bu avtomatik ko'ngilochar taxmin, yutuq kafolatlanmaydi. Mas'uliyat bilan o'ynang.")
