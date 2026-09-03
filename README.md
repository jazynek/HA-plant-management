# Plant Management (Home Assistant)

Własna integracja Home Assistant do zarządzania roślinami domowymi: strefa
stanowiska, historia przesadzeń i pielęgnacji, notatki, zdjęcia oraz
powiadomienia push (z przyciskami akcji) o podlewaniu i nawożeniu.
Zastępuje trackowanie na Trello.

## Co dostajesz

Dla każdej rośliny integracja tworzy jedno urządzenie ("device") z encjami:

- `sensor.<roślina>_status` — `ok` / `water_due` / `fertilize_due` /
  `both_due`, ze zdjęciem (`entity_picture`) i pełnymi atrybutami: gatunek,
  strefa, **wymagane nasłonecznienie** (`light_notes`), zasady
  podlewania/nawożenia (w tym miernik wilgotności, jeśli był podany),
  ostatnie/kolejne terminy, link do starej karty Trello oraz **historia**
  (ostatnie 20 zdarzeń: podlanie, nawożenie, przesadzenie, notatki, snooze).
- `sensor.<roślina>_kolejne_podlewanie`, `sensor.<roślina>_kolejne_nawozenie`,
  `sensor.<roślina>_ostatnie_podlewanie`, `sensor.<roślina>_ostatnie_nawozenie`
  — encje typu `date`, wygodne do automatyzacji i widoków kalendarza.
- `button.<roślina>_podlano` i `button.<roślina>_podlano_nawoz` — do
  ręcznego oznaczania z poziomu dashboardu.

Codziennie o skonfigurowanej godzinie integracja sprawdza, które rośliny
wymagają podlania/nawożenia i wysyła **jedno powiadomienie push na
telefon** (przez aplikację HA Companion) na roślinę, z przyciskami akcji:

- 💧 **Podlano**
- 💧🌱 **Podlano + Nawóz** (zaznacza jednocześnie podlanie i nawożenie)
- ⏭ **+1 dzień / +3 dni / +5 dni** (przesuwa najbliższy termin)

Treść powiadomienia zawiera też notatkę pielęgnacyjną dla danego terminu
(np. "rzadkie, sukulentowe — dokładnie osuszać podłoże; miernik: ok. 2"),
jeśli była zapisana przy roślinie (pole `watering_notes`/`fertilizing_notes`).

Naciśnięcie przycisku w powiadomieniu na telefonie od razu aktualizuje dane
w Home Assistant — nie trzeba nic dodatkowo konfigurować w automatyzacjach,
integracja sama nasłuchuje zdarzenia `mobile_app_notification_action`.

## Instalacja (HACS)

1. HACS → Integracje → menu (⋮) → **Custom repositories**.
2. Dodaj URL tego repozytorium (`https://github.com/jazynek/HA-plant-management`),
   kategoria **Integration**.
3. Zainstaluj "Plant Management", zrestartuj Home Assistant.
4. Ustawienia → Urządzenia i usługi → **Dodaj integrację** → "Plant Management".
   - **Usługa powiadomień**: nazwa usługi `notify.*` bez prefiksu, np. dla
     `notify.mobile_app_iphone_mateusza` wpisz `mobile_app_iphone_mateusza`.
     Sprawdzisz dokładną nazwę w Developer Tools → Actions, wpisując `notify.`.
   - **Godzina sprawdzania**: domyślnie `08:00:00`, format `HH:MM:SS`. Zmienisz
     ją później w Opcjach integracji.

Bez instalacji ręcznej (bez HACS) też zadziała: skopiuj katalog
`custom_components/plant_management` do `<config>/custom_components/` i
zrestartuj HA.

## Import roślin z Trello

W `data/trello_seed.json` znajdują się rośliny wyciągnięte z tablicy Trello
"Kwiatki" (gatunek, wymagane nasłonecznienie, zasady podlewania/nawożenia,
strefa oświetlenia, ostatnie/kolejne terminy, notatki o przesadzeniu, link
do oryginalnej karty Trello). Interwały podlewania/nawożenia zostały
oszacowane automatycznie z opisów po polsku — warto je przejrzeć i
skorygować po imporcie (`plant_management.update_plant`).

Ten plik **nie synchronizuje się automatycznie** z Trello — to
jednorazowy/ręcznie odświeżany eksport (patrz sekcja "Trello ↔ Home
Assistant" niżej dla planów na automatyzację tego).

### Import (nowe rośliny + aktualizacja istniejących)

```bash
export HA_URL=http://homeassistant.local:8123
export HA_TOKEN=<Long-Lived Access Token z Twojego profilu w HA>
python3 tools/import_trello_seed.py
```

Skrypt woła usługę `plant_management.import_seed`, która dodaje rośliny (i
ich encje) w jednym wywołaniu. **Bezpiecznie uruchomić ponownie** — import
dopasowuje rośliny po polu `name`: jeśli roślina o tej samej nazwie już
istnieje, jej dane są aktualizowane (bez duplikatu), a jeśli nie istnieje —
zostaje dodana.

### Usuwanie roślin, których już nie ma (zdechły / usunięte z Trello)

Import **nie usuwa** roślin, które zniknęły z `trello_seed.json` — trzeba
je usunąć jawnie, po dokładnej nazwie:

```bash
export HA_URL=http://homeassistant.local:8123
export HA_TOKEN=<token>
python3 tools/remove_plants.py "17. Tillandsia caput-medusae" "18. Tillandsia ionantha"
```

Można podać kilka nazw naraz. Nazwa musi być identyczna jak pole `name`
zapisane przy roślinie (widoczne jako nazwa urządzenia w HA).

### Nowe encje po aktualizacji integracji

Nowe typy encji (np. dodane w przyszłej wersji integracji) pojawiają się
dla już istniejących roślin dopiero po **restarcie Home Assistant** albo
przeładowaniu integracji (Ustawienia → Urządzenia i usługi → Plant
Management → ⋮ → Przeładuj) — sam import/update danych tego nie robi.

## Trello ↔ Home Assistant (plany na przyszłość)

Obecnie synchronizacja z Trello jest ręczna: trzeba wygenerować nowy
`data/trello_seed.json` (wymaga dostępu do Trello API/MCP) i uruchomić
import/usuwanie opisane wyżej. Wygodniejsza automatyzacja (np. okresowe
odpytywanie API Trello bezpośrednio z Home Assistant i pełna synchronizacja
dodań/usunięć/zmian) to temat na osobny etap prac — jeszcze nie
zaimplementowany.

Pole `zone` (aktualne stanowisko) zostało zaimportowane jako puste — w
Trello było oznaczone `[uzupełnij]` dla większości roślin. Uzupełnij je
przez usługę `plant_management.update_plant` albo z poziomu Developer Tools.

## Zdjęcia

Trello API do pobierania załączników nie było dostępne w tej sesji, więc
zdjęcia trzeba dodać ręcznie:

1. Wyeksportuj zdjęcia z kart w Trello (każda karta ma link
   `trello_url`/`trello_main_url` w danych seed — otwórz kartę i pobierz
   załącznik).
2. Wrzuć pliki do `<config>/www/plant_management/` w Home Assistant
   (utwórz folder, jeśli nie istnieje).
3. Ustaw pole `photo` na nazwę pliku, np.:

   ```yaml
   service: plant_management.update_plant
   data:
     plant_id: p_xxxxxxxx
     photo: monstera.jpg
   ```

   `plant_id` znajdziesz w atrybutach encji `sensor.<roślina>_status`
   (`unique_id` zawiera go, albo sprawdź w Developer Tools → States) —
   jeśli wolisz, dodaj też pomocniczą usługę wyszukania po nazwie z poziomu
   szablonu Jinja.

## Usługi

| Usługa | Opis |
|---|---|
| `plant_management.add_plant` | Dodaje nową roślinę |
| `plant_management.update_plant` | Aktualizuje pola istniejącej rośliny |
| `plant_management.remove_plant` | Usuwa roślinę i jej encje |
| `plant_management.mark_watered` | Zaznacza podlanie dziś |
| `plant_management.mark_fertilized` | Zaznacza nawożenie dziś |
| `plant_management.mark_watered_and_fertilized` | Zaznacza oba naraz |
| `plant_management.snooze_watering` | Przesuwa termin podlewania o `days` dni |
| `plant_management.snooze_fertilizing` | Przesuwa termin nawożenia o `days` dni |
| `plant_management.repot` | Zapisuje przesadzenie (data + notatka) |
| `plant_management.add_note` | Dodaje wpis do historii bez zmiany terminów |
| `plant_management.import_seed` | Masowy import listy roślin |

Pełne pola każdej usługi: `custom_components/plant_management/services.yaml`
(widoczne też w Developer Tools → Actions w UI Home Assistant).

## Ograniczenia i uwagi

- **iOS**: aplikacja HA Companion na iOS ogranicza liczbę przycisków akcji
  w powiadomieniu (zwykle do ok. 3-4). Jeśli przycisk "+5 dni" się nie
  mieści, użyj usługi `plant_management.snooze_watering`/`snooze_fertilizing`
  ręcznie albo skróć listę akcji w `__init__.py` (`_async_run_notification_check`).
- Dane roślin trzymane są lokalnie w `.storage/plant_management_plants` —
  kopia zapasowa HA (Ustawienia → System → Kopie zapasowe) obejmuje je
  automatycznie.
- To pierwsza wersja (v0.1.0): brak edycji z poziomu graficznego panelu
  (dodawanie/edycja roślin wyłącznie przez usługi) — jeśli chcesz karty
  Lovelace, najprostsza opcja to auto-wygenerowana strona urządzenia
  (Ustawienia → Urządzenia i usługi → Plant Management → wybierz roślinę)
  albo custom card typu `auto-entities`/`flex-table-card` grupująca
  wszystkie `sensor.*_status`.
