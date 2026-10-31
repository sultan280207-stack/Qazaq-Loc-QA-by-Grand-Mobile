#!/usr/bin/env bash
# Запускает настоящий `flutter gen-l10n` на ваших ARB-файлах во временном проекте.
# Ваши файлы не меняются, временный проект удаляется в конце.
#
#   scripts/gen_l10n_check.sh intl_ru.arb intl_kk_fixed.arb [intl_uz.arb ...]
#
# Первый файл считается исходником (шаблоном). Нужны Flutter и Python 3.
set -euo pipefail

if ! command -v flutter >/dev/null 2>&1; then
  echo "Flutter не найден. Установите его (https://docs.flutter.dev/get-started/install) и запустите снова." >&2
  exit 2
fi
if [ "$#" -lt 2 ]; then
  echo "Нужно минимум два файла: исходник и перевод. Например: $0 intl_ru.arb intl_kk_fixed.arb" >&2
  exit 2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
app="$tmp/l10n_check"

echo "Создаю временный проект..."
flutter create --project-name l10n_check --platforms=web --empty "$app" >/dev/null
mkdir -p "$app/lib/l10n"

# Язык берём из @@locale, а если его нет, из имени файла (intl_kk_fixed.arb -> kk).
locale_of() {
  python3 - "$1" <<'PY'
import json, re, sys
path = sys.argv[1]
try:
    loc = json.load(open(path, encoding="utf-8")).get("@@locale")
except Exception:
    loc = None
if not loc:
    m = re.match(r"intl_([A-Za-z]{2,3}(?:_[A-Z][a-z]{3})?)", path.rsplit("/", 1)[-1])
    loc = m.group(1) if m else "und"
print(loc)
PY
}

template=""
for f in "$@"; do
  loc=$(locale_of "$f")
  cp "$f" "$app/lib/l10n/intl_$loc.arb"
  echo "  $f -> intl_$loc.arb"
  [ -z "$template" ] && template="intl_$loc.arb"
done

cat > "$app/l10n.yaml" <<EOF
arb-dir: lib/l10n
template-arb-file: $template
output-dir: lib/l10n/gen
output-localization-file: app_localizations.dart
EOF

cd "$app"
flutter pub add flutter_localizations --sdk=flutter >/dev/null
flutter pub add intl:any >/dev/null
python3 - <<'PY'
p = "pubspec.yaml"
s = open(p, encoding="utf-8").read()
if "generate: true" not in s:
    s = s.replace("\nflutter:\n", "\nflutter:\n  generate: true\n", 1)
open(p, "w", encoding="utf-8").write(s)
PY

echo "Запускаю flutter gen-l10n..."
if flutter gen-l10n; then
  echo "Проверяю, что сгенерированный код собирается..."
  if flutter analyze --no-pub lib; then
    echo "Готово: gen-l10n прошёл, ошибок нет."
  else
    echo "gen-l10n прошёл, но в сгенерированном коде есть ошибки (см. выше)." >&2
    exit 1
  fi
else
  echo "flutter gen-l10n упал, причина выше." >&2
  exit 1
fi
