// SOCC-сцепление: реальная связь SOCC ⇆ торговая плоть, или только заимствование слов?
// Вопрос оператора (03.09): «SOCC автопилот, волны и прочее — мы что-то идейно черпаем, или моя
// система SOCC уже связана/влияет на то, что делаем?»
//
// Честный ответ требует улик по 6 осям. Веер ЧИТАТЕЛЕЙ (не мутируют, только read/grep/glob)
// → СВЕРКА ключевых притязаний независимыми скептиками → СИНТЕЗ классифицирует каждое сцепление
// как REAL (код/путь/схема/импорт) | ИДЕЙНОЕ (общие слова доктрины) | NOMINAL (названо, не связано).
// RUBICON: 0 записей, движок не трогаем. Никто ничего не пишет.
export const meta = {
  name: 'socc-coupling-audit',
  description: 'Аудит сцепления SOCC ⇆ торговые органы: REAL / идейное / NOMINAL',
  phases: [
    { title: 'Чтение', detail: '6 веерных читателей по осям сцепления' },
    { title: 'Сверка', detail: 'независимые скептики по ключевым притязаниям' },
    { title: 'Синтез', detail: 'классификация + честный вердикт' },
  ],
}

// ────────────────────────────── схемы ──────────────────────────────
const FIND = {
  type: 'object',
  properties: {
    scope: { type: 'string', description: 'название оси' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string', description: 'короткая формулировка сцепления-гипотезы' },
          kind_candidate: {
            type: 'string', enum: ['REAL', 'IDEATIONAL', 'NOMINAL', 'UNKNOWN'],
            description: 'предварительная классификация (скептик перепроверит)',
          },
          evidence: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                file: { type: 'string' },
                quote: { type: 'string', description: 'короткая цитата/строки, ≤240 символов' },
              },
              required: ['file', 'quote'],
            },
            description: 'файл+цитата. file — путь от корня репо. Для "пуст/нет" пиши file=путь и quote="(пусто/нет упоминаний)".',
          },
          why: { type: 'string', description: 'одно-два предложения, почему так классифицировано' },
        },
        required: ['claim', 'kind_candidate', 'evidence', 'why'],
      },
    },
  },
  required: ['scope', 'findings'],
}

const VERDICT = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'PLAUSIBLE'] },
          reason: { type: 'string' },
        },
        required: ['claim', 'verdict', 'reason'],
      },
    },
  },
  required: ['verdicts'],
}

const SYNTH = {
  type: 'object',
  properties: {
    rows: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          concept: { type: 'string', description: 'связываемое понятие (линия/отчёты/автопилот/волны/цикл/органы/доктрина/ДОМ)' },
          kind: { type: 'string', enum: ['REAL', 'IDEATIONAL', 'NOMINAL'] },
          evidence_short: { type: 'string' },
          one_line: { type: 'string', description: 'что это значит для оператора, ≤160 символов' },
        },
        required: ['concept', 'kind', 'evidence_short', 'one_line'],
      },
    },
    real_couplings: { type: 'array', items: { type: 'string' } },
    ideational: { type: 'array', items: { type: 'string' } },
    nominal: { type: 'array', items: { type: 'string' } },
    honest_verdict: { type: 'string', description: '3-5 предложений честного ответа оператору' },
  },
  required: ['rows', 'real_couplings', 'ideational', 'nominal', 'honest_verdict'],
}

// ────────────────────────────── общий контекст для читателей ──────────────────────────────
const CTX = `РЕПО: /Users/wavysexy/SOCC (private, ветка wave-shop).
Рабочая директория Bash = /Users/wavysexy/SOCC.
ВНИМАНИЕ к путаницам (проверь отдельно, не смшивай):
 - MEMORY_WAVE (ЗАГЛАВНЫМИ, корень: это дерево отчётов-памяти SOCC, внизу reports/…) — НЕ путать с memory_waves/ (строчными, крошечная директория спайна).
 - core/autopilot (под SOCC, reports/ и state/ ПУСТЫ) — НЕ путать с scripts/mint/arbiter/ymarket_autopilot_v1.py (ЖИВОЙ торговый автопилот, launchd).
 - core/socc/generated_megawaves (1 папка mw71…, похоже пуста/пустые receipts) и память-файлы «memory_effect» — НЕ путать с торговым wave_shop (ТГ-магазин) и веткой wave-shop.
Синтаксис: в Bash используй grep с КАВЫЧКАМИ вокруг паттернов и '*.py' (иначе zsh раскроет глоб). Ничего не пиши/не меняй — только чтение. Пути давай от корня репо. Цитируй коротко. Работай честно: если оси/связи нет — так и скажи с evidence "(пусто/нет)".`

// ────────────────────────────── читатели ──────────────────────────────
const READERS = [
  {
    key: 'line',
    prompt: `${CTX}

ОСЬ: ЛИНИЯ. Гипотеза: торговые оси ARBITER/OZON объявлены как экземпляры СХЕМЫ линии SOCC → реальная связь через схему и реестр.
Задачи:
1) Прочти SYSTEM/LINE_GOVERNANCE/LINE_GOVERNANCE_LINE_V1.json (schema=?), SYSTEM/LINE_GOVERNANCE/runtime/ACTIVE_LINES_REGISTRY_V1.json, SYSTEM/REGISTRY/LINE_REGISTRY_V1.json (статус RETIRED_SUPERSEDED?), scripts/socc/socc_lines_v1.py (куда указывает, что читает).
2) Прочти scripts/mint/arbiter/ARBITER_LINE_V1.json и OZON_MANAGER_LINE_V1.json — поле schema у них? purpose? Это формат socc.line.v1?
3) Найди, где читается ARBITER_LINE_V1.json / ACTIVE_LINES_REGISTRY кодом или каноном. Является ли ARBITER зарегистрированной линией SOCC (входит в реестр активных линий) или это декорация-файл, который никто не читает?
4) Глянь SYSTEM/LINE_GOVERNANCE/LINE_GOVERNANCE_ROADMAP.md — есть ли там ARBITER/MINT как цель?
Вывод: REAL (линия ARBITER структурно = линия SOCC по схеме и реестру) / IDEATIONAL (только формат-имя) / NOMINAL (файл-сирота). Дай 3-6 findings с evidence.`,
  },
  {
    key: 'reports_anchor',
    prompt: `${CTX}

ОСЬ: ЯКОРЬ ОТЧЁТОВ = MEMORY_WAVE/reports/mint/arbiter. Гипотеза: канонические отчёты торговых органов физически лежат В ДЕРЕВЕ ПАМЯТИ SOCC (MEMORY_WAVE) → торговые артефакты внутри структуры памяти SOCC = реальная связь.
Задачи:
1) Какие модули (arbiter/socc_cli/scripts) ПИШУТ или ЧИТАЮТ под MEMORY_WAVE/reports/mint/arbiter/… ? Найди функцию-определитель корня отчётов (например _reports_root, REPORTS). grep по 'MEMORY_WAVE/reports' и по 'reports/mint'.
2) Что такое MEMORY_WAVE в целом: это дерево отчётов-памяти SOCC? Прочти START_HERE.md и верх MEMORY_WAVE (если есть README). Есть ли внутри reports/autonomy (отчёты само-постройки core/socc) рядом с reports/mint (торговля) — ОДНО дерево?
3) reports/mint/arbiter содержит что? ymarket_tasks.json (реестр ЗАДАНИЙ), ymarket_autopilot.log, леджеры магазинов — канон торговли живёт под якорем SOCC-памяти?
4) Есть ли у memory_waves/ (строчными) или knowledge_spine отношение к MEMORY_WAVE/reports — одна система памяти или разные?
Вывод: REAL если торговые отчёты и их якорь физически внутри дерева памяти SOCC и/или тот же механизм. Дай 3-6 findings.`,
  },
  {
    key: 'autopilot_word',
    prompt: `${CTX}

ОСЬ: СЛОВО «АВТОПИЛОТ». Гипотеза оператора: «SOCC автопилот» связан с нашим торговым автопилотом. Проверь честно, что это за два объекта.
Задачи:
1) core/autopilot/ — что внутри? (reports/, state/ пусты?) Найди файлы. Если пусто — скажи прямо. Есть ли код/канон, который что-то пишет/читает в core/autopilot? grep по 'core/autopilot'.
2) Есть ли в core/socc органы с именем autopilot/сам-ход (autonomous_*, daemon, background_shadow_runtime, self_building)? Это живые машины (файлы-состояния, кого-то читают) или церемониальные (proof/status, но не код исполнения)? Кратко по 3-5 папкам core/socc с доказательствами (что внутри: json-состояние? код? пусто?).
3) scripts/mint/arbiter/ymarket_autopilot_v1.py — ЖИВОЙ торговый автопилот: что он делает, кем запускается (launchd/суточный цикл), читает ли core/autopilot или core/socc? (Уже знаю: он сухой, RUBICON, 0₽, но подтверди — импортирует core? НЕТ/ДА.)
4) Где ещё в репо слово «автопилот» (каноны, socc_mint_autopilot_* под scripts/mint) — торговый смысл?
Вывод: слово общее или два разных объекта с одним именем? REAL-связи кода между core/autopilot и торговым автопилотом НЕТ или есть? Дай 3-6 findings с evidence (файл+строка).`,
  },
  {
    key: 'waves',
    prompt: `${CTX}

ОСЬ: «ВОЛНЫ». Оператор спрашивает про «волны». Найди ВСЕ употребления понятия wave/волн/megawave по репо и классифицируй, ЧТО это в каждом месте.
Задачи:
1) core/socc/generated_megawaves/ — что это? (mw71_…/receipts — есть файлы? пусто?) Что за «волны» тут рождаются? Прочти любой текстовый файл внутри. Есть ли рядом канон про megawave (grep -ri 'megawave' по core SYSTEM).
2) memory_waves/socc/*.memory.json — что за файл (memory_effect)? Как относится к «волнам памяти»?
3) scripts/mint/wave_shop/ (ТГ-магазин) и ветка wave-shop + git-пользователь wavy2wave + каталог пользователя /Users/wavysexy — это БРЕНД оператора «wavy», не концепт SOCC? Проверь wave_shop/GO_LIVE.md и config — что там про волну.
4) «волна» в git-логах торговли (например «вторая волна гейтов») и в ymarket_tree_v1.json / _digest_extracts.json — разговорное «волна работ»?
5) Есть ли в SYSTEM/FOUNDATION/SOVEREIGN канон-определение «волны» как механизма SOCC? grep -ri 'волн' --include='*.md' по SYSTEM core FOUNDATION. Если единственные находки — разговорные/брендовые, так и скажи.
Вывод: разложи по полочкам: (а) megawave SOCC (реальное/пустое?), (б) волны-памяти memory_waves, (в) бренд wavy/wave_shop, (г) разговорная «волна работ». Дай 4-8 findings.`,
  },
  {
    key: 'socc_cli_reads_core',
    prompt: `${CTX}

ОСЬ: ДОМ/CLI читает ЯДРО SOCC. Гипотеза: поверхности socc_cli (которые оператор называет «наша система» = живой CLI ДОМ/ЯМ-ЦИКЛ) структурно читают состояние core/socc → реальная связь интерфейса с ядром SOCC.
Задачи:
1) socc_cli/*.py: home.py, runner.py, tui.py, cli.py, brain.py читают core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json, approved_autonomy_lane_runner/proof, hermes_repair, autonomy/self_building/status_panel (см. ROUTE/PROOF_DIR/HERMES_*/SB_*). Подтверди эти константы (прочти 5-10 строк каждого). Что эти файлы ядра содержат (живое состояние? вердикты proof?).
2) Эти core-файлы СУЩЕСТВУЮТ и непусты? (ls -la, head). CURRENT_ROUTE_AUTHORITY.json большой? autonomy_pulse? Что реально показывает оператору (команда «socc агент»/runner/tui)?
3) Являются ли чтения этих ядерных путей частью ЖИВОГО пути оператора (запуск dom/eco/pult/home в ДОМЕ ЯМ-ЦИКЛ) или только побочные экраны-витрины церемонии?
4) Где ТОРГОВАЯ плоть (scripts/mint/arbiter) и socc_cli встречаются: ДОМ читает торговые стора (stores.json, леджеры) И ядро SOCC одновременно? Один интерфейс = два источника?
Вывод: REAL если CLI-лицо системы показывает/читает состояние ядра SOCC в живом пути. Дай 3-6 findings с evidence (переменная→путь→файл, что в файле).`,
  },
  {
    key: 'doctrine_tokens',
    prompt: `${CTX}

ОСЬ: ДОКТРИНАЛЬНЫЕ СЛОВА. Гипотеза: правила торговых органов (RUBICON, сухо-авто/живьё-по-слову, dry/commit, evidence без фейк-пасс, owner-«удавка», орган, честно/без выдумки) — кодифицированы в канонах SOCC (первоисточник) ИЛИ придуманы в торговле, а SOCC лишь перекликается?
Задачи:
1) Найди где впервые/кодифицированы: RUBICON, «по слову», dry/commit, фейк-пасс, evidence. Ищи по SYSTEM/*.md и core/socc (route_authority доктрины, SOVEREIGN), по 'RUBICON', 'не выдумыва', 'фейк', 'по слову', 'сухо'.
2) Прочти SYSTEM/STATUS/CURRENT_PROJECT_ORDER_V1.md — он упоминает MINT/ARBITER/сухо? Это связующий канон статуса?
3) Торговые органы ymarket_office_v1.py и arbiter_console_v1.py делают sys.path.insert(..., SYSTEM/INTERFACE/dashboard) — что импортируют оттуда? Это импорт КАНОНА SOCC в торговый код? (прочти импорты).
4) Реестр ЗАДАНИЙ (ymarket_tasks_v1.py): «owner = орган = удавка», «без фейк-пасс», «идемпотентно по хешу намерения» — эти ПОНЯТИЯ встречаются в SOCC-каноне (орган, ячейка, гейт, удавка, хеш намерения) или рождены в торговле? Сравни формулировки: SYSTEM/REGISTRY/ENTITY_REGISTRY_V1.json, CELL_REGISTRY, core/socc (creator_external_decision_gate, role_gated_runner — «гейт создателя» = «по слову оператора»?).
Вывод: раздели: (а) доктрина SOCC → торговые органы (текстовое наследование), (б) изобретено в торговле и записано в каноны арбитра, (в) пустое созвучие. Дай 4-8 findings с evidence.`,
  },
]

// ────────────────────────────── тело ──────────────────────────────
phase('Чтение')
const read_results = await parallel(
  READERS.map(r => () =>
    agent(r.prompt, { label: `read:${r.key}`, phase: 'Чтение', schema: FIND })
      .then(res => (res ? { ...res, scope: res.scope || r.key } : null))
  )
)
const readers = read_results.filter(Boolean)

// собрать все findings для сверки (первичная классификация от читателя)
const all = readers.flatMap(r => (r.findings || []).map(f => ({ ...f, _scope: r.scope })))
log(`Читатели вернули ${readers.length}/${READERS.length}; findings: ${all.length}`)

// Сверка: независимые скептики по ПЕРВИЧНЫМ притязаниям (не дублируют читателя —
// перечитывают файлы и пытаются опровергнуть). Чанкуем на 3 группы.
const CHUNKS = 3
const chunks = Array.from({ length: CHUNKS }, (_, i) => all.filter((_, j) => j % CHUNKS === i))
const CLAIM_LINE = c =>
  `CLAIM [${c.kind_candidate}] «${c.claim}» (ось ${c._scope})` +
  (c.evidence || []).map(e => `\n  — ${e.file}: ${e.quote}`).join('')

phase('Сверка')
const verify_results = await parallel(
  chunks.map((chunk, i) => () => {
    if (!chunk.length) return Promise.resolve(null)
    return agent(
      `${CTX}

Ты — НЕЗАВИСИМЫЙ СКЕПТИК аудита сцепления SOCC⇆торговля. Перед тобой притязания читателя. Твоя работа — ПЕРЕПРОВЕРИТЬ каждое: открой сами файлы, посмотри, существует ли связь на самом деле. Будь строг:
 - CONFIRMED = перепроверил, связь/пустота реальна (цитата сходится).
 - PLAUSIBLE = правдоподобно, но не смог полностью подтвердить по файлам.
 - REFUTED = притязание ложно (читатель ошибся/свёл не то/связи нет).
Особо проверяй: реально ли файл-сирота (никто не читает), реально ли пуста директория, реально ли импорт/чтение пути, не перепутал ли читатель MEMORY_WAVE с memory_waves и core/autopilot с ymarket_autopilot.

${chunk.map(CLAIM_LINE).join('\n\n')}

Верни verdicts по КАЖДОМУ claim (сохрани формулировку claim как есть).`,
      { label: `verify:${i + 1}`, phase: 'Сверка', schema: VERDICT }
    )
  })
)
const verdicts = verify_results.filter(Boolean).flatMap(v => (v.verdicts || []).map(x => x))

// классификация: пометить каждый claim вердиктом (по умолчанию UNVERIFIED)
const byClaim = new Map()
all.forEach(c => byClaim.set(c.claim, { ...c, _verdict: 'UNVERIFIED' }))
verdicts.forEach(v => {
  const hit = byClaim.get(v.claim)
  if (hit) hit._verdict = v.verdict
})

const verdict_count = { CONFIRMED: 0, PLAUSIBLE: 0, REFUTED: 0, UNVERIFIED: 0 }
Object.values(byClaim).forEach(c => { verdict_count[c._verdict] = (verdict_count[c._verdict] || 0) + 1 })
log(`Сверка: ` + Object.entries(verdict_count).map(([k, v]) => `${k}=${v}`).join(' · '))

// Синтез: консолидированный итог для оператора
phase('Синтез')
const synth_payload = {
  verdict_count,
  findings: Object.values(byClaim).map(c => ({
    claim: c.claim, scope: c._scope, kind_candidate: c.kind_candidate,
    verdict: c._verdict, evidence: c.evidence, why: c.why,
  })),
}
const synth = await agent(
  `${CTX}

Ты — СИНТЕЗАТОР аудита «связана ли система SOCC с торговой плотью или мы только черпаем слова».

Ниже — findings от 6 читателей + вердикты независимых скептиков. Прочти внимательно, взвесь: REFUTED-притязания отбрасывай, PLAUSIBLE отмечай как слабое, CONFIRMED держи как улику.
Задача: дать ОПЕРАТОРУ честную классификацию по понятиям (строка rows): ЛИНИЯ, ОТЧЁТЫ/якорь MEMORY_WAVE, АВТОПИЛОТ, ВОЛНЫ, ДОМ/CLI⇆ядро SOCC, ДОКТРИНА/RUBICON/удавка/орган, (и что ещё видишь).
kind = REAL (код/путь/схема/импорт — проверено) | IDEATIONAL (общие слова/доктрина, структурной связи нет) | NOMINAL (названо, не связано / церемония / пусто).
Потом honest_verdict — 3-5 предложений ЧЕСТНОГО ответа на вопрос оператора, на русском, без лести и без приукрашивания: где связь РЕАЛЬНА (схема линии, якорь отчётов в дереве памяти SOCC, ДОМ читает ядро), где мы лишь «идейно черпаем» (общее слово «автопилот», разговорные волны), а где SOCC-механика церемониальна/пуста (core/autopilot пуст, megawaves пусты, если так) и НЕ влияет на торговлю, хотя называется теми же словами. real_couplings/ideational/nominal — списки коротких формулировок.

payload:
${JSON.stringify(synth_payload, null, 1)}`,
  { label: 'synthesize', phase: 'Синтез', schema: SYNTH, effort: 'high' }
)

return { readers: readers.length, findings: all.length, verdict_count, synth }
