"""Shared API errors and Ukrainian messages, independent of project storage."""


# Messages of the timeline's checks (here, graphics.py, joins.py) as the author reads them: the studio speaks Ukrainian.
UKRAINIAN = {
    "Invalid typography": "Невірні налаштування шрифту каналу",
    "Invalid source offset": "Невірний початок фрагмента у файлі",
    "Invalid timed text layout": "Невірне розташування слів тексту",
    "Invalid timed text word": "Невірне слово тексту",
    "Timed text words must be ordered": "Слова тексту мають іти по черзі",
    "Timed text words need a positive box": "Слово тексту має мати розмір",
    "Timed text differs from clip text": "Слова не збігаються з текстом кліпу",
    "Invalid frame members": "Невірний склад кадру",
    "Frame title is empty": "Назва кадру порожня",
    "Invalid frame role": "Невідома роль кадру",
    "Frame group not found": "Кадр не знайдено",
    "Invalid mute state": "Невірний стан звуку",
    "Invalid visibility state": "Невірний стан видимості доріжки",
    "This layer has no picture": "На цій доріжці немає зображення",
    "This layer has no sound": "На цьому шарі немає звуку",
    "Stack group not found": "Групу не знайдено",
    "Invalid stack reference": "Невірне посилання на шар",
    "Invalid stack destination": "Невірне місце для шару",
    "Source offset is after the end of the file": "Початок фрагмента пізніше за кінець файлу",
    "Timed words require a text clip": "Слова з часом бувають лише в текстовому кліпі",
    "Invalid text role": "Невідома роль тексту",
    "Text frame is missing from the approved plan": "Текстового кадру немає в плані",
    "A text frame must contain its complete spoken passage": "Текстовий кадр має містити всі свої слова озвучки",
    "A text frame must begin with its first spoken word": "Текстовий кадр має починатися з першого слова озвучки",
    "Invalid batch size": "Забагато або замало дій за раз",
    "Unsupported batch action": "Ця дія не підтримується в пакеті",
    "Waveform requires audio": "Хвиля звуку буває лише в аудіо чи відео",
    "Invalid graphics value": "Невірне значення графіки",
    "Unknown mask": "Невідома маска",
    "Unknown font": "Невідомий шрифт",
    "Invalid text alignment": "Невідоме вирівнювання тексту",
    "Invalid gradient": "Невірний градієнт",
    "Invalid shadow color": "Невірний колір тіні",
    "Invalid shadow": "Невірна тінь",
    "Scene not found": "Кадр не знайдено",
    "Invalid transition endpoint": "Невірний край переходу",
    "A transition requires visual clips": "Перехід можливий лише між картинками чи відео",
    "Transitions can only be dropped onto touching frame edges": "Перехід ставиться лише на стик сусідніх кадрів",
    "Unknown transition": "Невідомий перехід",
    "Transition is longer than an adjacent frame": "Перехід довший за сусідній кадр",
}


class StudioError(Exception):
    def __init__(self, message, status=400):
        message = UKRAINIAN.get(str(message), message)
        if isinstance(message, str) and message.startswith(("Unknown visual effect", "Frame exceeds", "Invalid ")) and message not in UKRAINIAN.values():
            message = "Невірні параметри: " + message   # a rare check without a translation still says it is the input
        super().__init__(message)
        self.status = status
