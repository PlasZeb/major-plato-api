# Oktatói naplózás

A naplók a `LOG_REPO` privát GitHub-tároló `sessions` mappájába kerülnek.
Alapértelmezett tároló: `PlasZeb/major-plato-logs`.
Minden játékmenethez három, egyetlen Git-commitban frissített fájl tartozik:

- `README.md`: GitHubon olvasható döntéstörténet és értékelés;
- `decisions.csv`: UTF-8 BOM, pontosvesszővel tagolt, Excelben megnyitható táblázat;
- `session.json`: teljes strukturált napló, eredeti parancs, állapot, értékelés és pontadatok.

## Mi automatikus?

A `/turn` minden új körének eredeti parancsa már az MI-hívás előtt tartósan bekerül.
Az értékelést a térképes parancs kiadása előtt mentjük. A végén a dispatch eredményét
és a játékosnak küldött választ is mentjük. A `queued` nem jelent megérkezést.
Az új értékelési és pontmezőket eltávolítjuk a játékos válaszából és a térképre mentett
állapotból/eseményből. Nincs oktatói naplólekérdező HTTP-végpont.
A korábbi, már térképre mentett értékelésekre ez nem visszamenőleges törlés.
Az MI utasítást kap arra is, hogy a játékosnak szánt narratívába ne írjon pontokat
vagy oktatói értékelést; a szabad szöveg tartalma ettől még modellfüggő.

A közvetlen térkép-API mozgatásai nem mennek át ezen a döntési motoron.
A külön Custom GPT továbbra is meg kell hogy hívja az `/append_log` actiont:
annak szerkesztői utasításait a backend telepítése nem módosítja.

## Meglévő Custom GPT napló

Az `/append_log` továbbra is elfogadja a `player`, `unit`, `decisions` mezőket.
Opcionálisan küldhető `session_id` és `scenario_id`: mindig ugyanazt a session_id-t
kell használni egy teljes játék alatt. Enélkül csak az adott beküldött döntéscsomagot
lehet biztosan összekapcsolni. Az azonos döntéssor ismételt beküldése nem duplikálódik.
A legacy adatok külön `legacy:` névtérben, önbevallott adatokként tárolódnak;
nem írhatják felül a `/turn` motor hitelesített térképes játékának történetét.
Az eredeti három szám `reported_scores` alatt, illetve a CSV `*_reported` oszlopaiban
megmarad. A régi séma nem mondja meg, hogy változás vagy összpont, ezért nem számolunk
belőlük önkényesen új összpontszámot. A régi `logs` mappa fájljai megmaradnak.

## Pontozási szabályok

Nem találtunk hiteles pontozási rubrikát a backendben. Ezért alaphelyzetben az új motor
szöveges értékelést ment; a numerikus pontok `null` / „nincs értékelve” értéket kapnak.
Ez nem nulla pontot jelent. A rendszer nem talál ki új oktatási skálát.

A `SCORING_RUBRIC_JSON` szerverváltozóval bekapcsolható a meglévő oktatói rubrika.
Kötelező mezők: `version` (szöveg), `instructions` (a teljes értékelési szabály),
`axes.ethical`, `axes.military`, `axes.command`; mindegyik tengelyhez egész számú
`initial`, `min`, `max`, `max_delta` kell. A konkrét számokat az oktató eredeti
szabályrendszeréből kell átvenni. Nincs éles alapértelmezett mintapontozás.

A rubrikát az első naplózott körben rögzítjük a játékmenethez. Menet közben nem cseréljük
ki. A modell pontváltozást javasol, a szerver ellenőrzi annak tartományát, és számítja az
előtte/változás/utána értékeket. A korlátozott tényleges változás és a modell javaslata
külön mező. Hiányzó értékelés után nem gyártunk folyamatos pontszámtörténetet.
A korábbi játék pontjait nem vezetjük le a narratívából. Bekapcsolás után új játékot
kell indítani a hiteles kezdőértékhez.

## Render-beállítások és hozzáférés

Használja a már meglévő `GITHUB_TOKEN` és `LOG_REPO` változókat; a token csak a szerveren
marad. A tokennek a privát naplótároló tartalmához írási/olvasási jog kell.
A backend minden archiválási műveletsor előtt ellenőrzi, hogy a tároló privát.
Csak a GitHubon hozzáférő oktatók nyithatják meg a naplót.
Ne oszd meg a tárolót játékosokkal, ha az értékeléseket nem láthatják.

## Hibák és megismételt kérések

A kliens ugyanazzal a `turn_id`-val próbálja újra ugyanazt a kérést.
A befejezett kör újraküldése a már mentett játékosválaszt adja vissza; nem hív újra MI-t,
nem ad ki új parancsot és nem számít újra pontot. A Git ref frissítése nem kényszerített:
ütközéskor újraolvasunk, így más játék naplóját sem írjuk felül.

Ha a GitHub már a kezdeti mentéskor nem elérhető, a kör nem indul el, 503 hibát kap.
Ha a kiadás után megszakad a folyamat, a `dispatching` vagy `needs_review` állapot
megmarad. Ilyenkor nem ismétlünk automatikusan egy esetleg már kiadott parancsot.
Oktatói ellenőrzésig az adott session új körei is blokkoltak; más session indítható.
A `processing` egy folyamatleállás után szintén maradhat függőben. Nincs időzített
háttér-újrapróbálkozás vagy automatikus helyreállítás a két szolgáltatás között.
A `failed_before_dispatch` után új turn_id-val biztonságosan újrapróbálható a kör.

## Ellenőrzés

`python -m unittest -v test_decision_archive` a backend függőségeivel.
A tesztek helyi GitHub/MI/térkép-helyettesítőkkel futnak, nem írnak éles játéknaplót.
Élesítés után `/health` tartalmazza: `decision_archive_version: "1"`.
Egy új valódi `/turn` után ellenőrizni kell az új session három fájlját a GitHubon.
