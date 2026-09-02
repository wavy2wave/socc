# Как подключить доступ WAVE

Инструкция для клиента. Отдавать вместе с ключом — или положить ссылкой в боте.

> **Быстрее всего:** нажмите в боте «⚡️ Подключить» — он пришлёт готовый конфиг
> под ваш инструмент, вписывать руками ничего не нужно. Эта страница — на случай,
> если хотите сделать вручную или вашего инструмента нет в списке.

---

## Что вы получили

**Ключ доступа** вида `wave-xxxxxxxxxxxxxxxxxxxx` — это ваш личный ключ.
Он работает как обычный OpenAI-ключ: любой инструмент, умеющий работать с
OpenAI-совместимым API, подключается за 30 секунд.

Нужно поменять **две вещи**: адрес сервера и ключ.

```
base_url:  https://ВАШ_ДОМЕН/v1
api_key:   wave-xxxxxxxxxxxxxxxxxxxx
```

**Ключ не меняется при продлении.** Настроили один раз — больше к настройкам
возвращаться не нужно, даже когда тариф продлевается.

---

## Cursor

1. `Settings` → `Models` → прокрутить до **OpenAI API Key**
2. Включить `Override OpenAI Base URL`
3. В поле Base URL: `https://ВАШ_ДОМЕН/v1`
4. В поле API Key: ваш ключ `wave-...`
5. Нажать `Verify` → должно стать зелёным

---

## Continue (VS Code / JetBrains)

Откройте `~/.continue/config.json` и добавьте в `models`:

```json
{
  "models": [
    {
      "title": "Claude Opus 5 (WAVE)",
      "provider": "openai",
      "model": "claude-opus-5",
      "apiBase": "https://ВАШ_ДОМЕН/v1",
      "apiKey": "wave-xxxxxxxxxxxxxxxxxxxx"
    }
  ]
}
```

---

## Python

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://ВАШ_ДОМЕН/v1",
    api_key="wave-xxxxxxxxxxxxxxxxxxxx",
)

response = client.chat.completions.create(
    model="claude-opus-5",
    messages=[{"role": "user", "content": "Привет!"}],
)
print(response.choices[0].message.content)
```

---

## JavaScript / TypeScript

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://ВАШ_ДОМЕН/v1",
  apiKey: "wave-xxxxxxxxxxxxxxxxxxxx",
});

const res = await client.chat.completions.create({
  model: "claude-opus-5",
  messages: [{ role: "user", content: "Привет!" }],
});
console.log(res.choices[0].message.content);
```

---

## curl

```bash
curl https://ВАШ_ДОМЕН/v1/chat/completions \
  -H "Authorization: Bearer wave-xxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-5",
    "messages": [{"role": "user", "content": "Привет!"}]
  }'
```

---

## Личный кабинет

Откройте `https://ВАШ_ДОМЕН_КАБИНЕТА`, введите свой ключ — увидите:

- какой у вас тариф
- сколько токенов осталось (или что тариф безлимитный)
- сколько времени осталось
- сколько запросов сделано

Ключ сохраняется только в вашем браузере.

---

## Частые вопросы

**Какие модели доступны?**
`claude-opus-5`, `claude-opus-4-8`. Список активных моделей — запросом
`GET /v1/models` с вашим ключом.

**Что значит «справедливое использование» на безлимите?**
До 700 000 единиц в сутки. Это полный рабочий день с большим запасом.
Ограничение защищает сервис от автоматических циклов и не мешает живой работе.
Счётчик обновляется каждые сутки автоматически.

**Токены закончились / тариф истёк.**
Откройте бот и продлите — **новый ключ не нужен**, доступ возобновится на том же.
Ничего перенастраивать не придётся.

**Ключ не работает.**
Проверьте: (1) скопирован целиком, вместе с `wave-`; (2) в base_url есть `/v1`
на конце; (3) в кабинете тариф активен. Если всё так — напишите в поддержку.

**Можно пользоваться с нескольких устройств?**
Да. Ключ не привязан к устройству — лимит общий на тариф.

**Стриминг (stream: true)?**
Пока отключается автоматически: ответ приходит целиком. Это нужно для точного
учёта расхода.

---

## Поддержка

Вопросы — в бот, раздел «Помощь».
