import os
import argparse
from pathlib import Path

# ========================= КОНФИГУРАЦИЯ =========================
# Флаг: включать все файлы или только указанные
INCLUDE_ALL_FILES = True  # True - все файлы, False - только из списка ниже

# Список файлов для включения (если INCLUDE_ALL_FILES = False)
FILES_TO_INCLUDE = [
    # "config.py",
    # "main_network_new.py.py",
]


# ================================================================


def collect_code(args):
    root_path = Path(args.root_dir).resolve()
    output_path = root_path / args.output

    # Расширения по умолчанию (используются только если INCLUDE_ALL_FILES = True)
    if not args.extensions:
        extensions = {".py", ".yaml", ".yml", ".ini", ".cfg", ".toml"}
    else:
        extensions = set(args.extensions)

    # Исключаемые директории
    exclude_dirs = {".git", "__pycache__", ".idea", ".pytest_cache",
                    "venv", "env", ".venv", "node_modules", "dist", "build"}
    exclude_dirs.update(args.exclude_dirs)

    files_collected = 0

    with open(output_path, 'w', encoding='utf-8') as outfile:
        # Заголовок
        outfile.write(f"ПРОЕКТ: {root_path.name}\n")
        outfile.write(f"РЕЖИМ: {'ВСЕ ФАЙЛЫ' if INCLUDE_ALL_FILES else 'ВЫБОРОЧНЫЙ'}\n")
        outfile.write(f"КОРНЕВАЯ ДИРЕКТОРИЯ: {root_path}\n")
        outfile.write("=" * 100 + "\n\n")

        # Режим 1: Все файлы
        if INCLUDE_ALL_FILES:
            file_paths = sorted(root_path.rglob("*"))

        # Режим 2: Только указанные файлы
        else:
            file_paths = []
            for file_pattern in FILES_TO_INCLUDE:
                # Ищем файл по паттерну (поддержка wildcards)
                found_files = list(root_path.rglob(file_pattern))
                if found_files:
                    file_paths.extend(found_files)
                else:
                    # Пробуем как относительный путь
                    file_path = root_path / file_pattern
                    if file_path.exists():
                        file_paths.append(file_path)
                    else:
                        print(f"⚠️ Файл не найден: {file_pattern}")

            file_paths = sorted(set(file_paths))  # Удаляем дубликаты

        # Обход найденных файлов
        for file_path in file_paths:
            # Пропускаем исключенные директории
            if any(exclude_dir in file_path.parts for exclude_dir in exclude_dirs):
                continue

            # Пропускаем не файлы
            if not file_path.is_file():
                continue

            # В режиме "все файлы" проверяем расширение
            if INCLUDE_ALL_FILES and file_path.suffix.lower() not in extensions:
                continue

            # Пропускаем файлы меньше минимального размера
            if file_path.stat().st_size < args.min_size:
                continue

            try:
                relative_path = file_path.relative_to(root_path)

                # Разделитель файла
                outfile.write("\n" + "=" * 100 + "\n")
                outfile.write(f"ФАЙЛ: {relative_path}\n")
                outfile.write(f"ПУТЬ: {file_path}\n")
                outfile.write(f"РАЗМЕР: {file_path.stat().st_size} байт\n")
                outfile.write("=" * 100 + "\n\n")

                # Чтение содержимого
                with open(file_path, 'r', encoding='utf-8') as infile:
                    content = infile.read()

                    # Добавление нумерации строк
                    if args.line_numbers:
                        lines = content.split('\n')
                        numbered_content = "\n".join(
                            f"{i + 1:4d} | {line}" for i, line in enumerate(lines)
                        )
                        outfile.write(numbered_content)
                    else:
                        outfile.write(content)

                outfile.write("\n" + "-" * 100 + "\n")
                files_collected += 1

            except Exception as e:
                outfile.write(f"[Ошибка при обработке файла {file_path}: {e}]\n")

    print(f"✅ Собрано {files_collected} файлов в {output_path}")
    if not INCLUDE_ALL_FILES:
        print(f"📁 Режим: выборочный ({len(FILES_TO_INCLUDE)} файлов в списке)")


def main():
    parser = argparse.ArgumentParser(description="Сбор кода проекта в один файл")
    parser.add_argument("-o", "--output", default="project_code.txt",
                        help="Имя выходного файла")
    parser.add_argument("-r", "--root-dir", default=".",
                        help="Корневая директория проекта")
    parser.add_argument("-e", "--extensions", nargs="+",
                        help="Расширения файлов для включения (только в режиме 'все файлы')")
    parser.add_argument("--exclude-dirs", nargs="+", default=[],
                        help="Дополнительные директории для исключения")
    parser.add_argument("--min-size", type=int, default=0,
                        help="Минимальный размер файла в байтах")
    parser.add_argument("--line-numbers", action="store_true",
                        help="Добавить нумерацию строк")

    args = parser.parse_args()

    # Информация о текущем режиме
    print(f"🎯 Режим работы: {'ВСЕ ФАЙЛЫ' if INCLUDE_ALL_FILES else 'ВЫБОРОЧНЫЙ'}")
    if not INCLUDE_ALL_FILES:
        print(f"📋 Файлы для включения ({len(FILES_TO_INCLUDE)}):")
        for f in FILES_TO_INCLUDE:
            print(f"  - {f}")

    collect_code(args)


if __name__ == "__main__":
    main()



# import os
# import argparse
# from pathlib import Path
#
#
# def collect_code(args):
#     root_path = Path(args.root_dir).resolve()
#     output_path = root_path / args.output
#
#     # Расширения по умолчанию
#     if not args.extensions:
#         extensions = {".py", ".txt", ".md", ".yaml", ".yml", ".json", ".ini", ".cfg", ".toml"}
#     else:
#         extensions = set(args.extensions)
#
#     # Исключаемые директории
#     exclude_dirs = {".git", "__pycache__", ".idea", ".pytest_cache",
#                     "venv", "env", ".venv", "node_modules", "dist", "build"}
#     exclude_dirs.update(args.exclude_dirs)
#
#     files_collected = 0
#
#     with open(output_path, 'w', encoding='utf-8') as outfile:
#         # Заголовок
#         outfile.write(f"ПРОЕКТ: {root_path.name}\n")
#         outfile.write(f"ВРЕМЯ СОЗДАНИЯ: {Path(__file__).stat().st_ctime}\n")
#         outfile.write(f"КОРНЕВАЯ ДИРЕКТОРИЯ: {root_path}\n")
#         outfile.write("=" * 100 + "\n\n")
#
#         # Обход файлов
#         for file_path in sorted(root_path.rglob("*")):
#             # Пропускаем исключенные директории
#             if any(exclude_dir in file_path.parts for exclude_dir in exclude_dirs):
#                 continue
#
#             # Пропускаем файлы меньше минимального размера
#             if file_path.is_file() and file_path.stat().st_size < args.min_size:
#                 continue
#
#             # Проверяем расширение файла
#             if file_path.is_file() and file_path.suffix.lower() in extensions:
#                 try:
#                     relative_path = file_path.relative_to(root_path)
#
#                     # Разделитель файла
#                     outfile.write("\n" + "=" * 100 + "\n")
#                     outfile.write(f"ФАЙЛ: {relative_path}\n")
#                     outfile.write(f"ПУТЬ: {file_path}\n")
#                     outfile.write(f"РАЗМЕР: {file_path.stat().st_size} байт\n")
#                     outfile.write("=" * 100 + "\n\n")
#
#                     # Чтение содержимого
#                     with open(file_path, 'r', encoding='utf-8') as infile:
#                         content = infile.read()
#
#                         # Добавление нумерации строк
#                         if args.line_numbers:
#                             lines = content.split('\n')
#                             numbered_content = "\n".join(
#                                 f"{i + 1:4d} | {line}" for i, line in enumerate(lines)
#                             )
#                             outfile.write(numbered_content)
#                         else:
#                             outfile.write(content)
#
#                     outfile.write("\n" + "-" * 100 + "\n")
#                     files_collected += 1
#
#                 except Exception as e:
#                     outfile.write(f"[Ошибка при обработке файла {file_path}: {e}]\n")
#
#     print(f"✅ Собрано {files_collected} файлов в {output_path}")
#
#
# def main():
#     parser = argparse.ArgumentParser(description="Сбор кода проекта в один файл")
#     parser.add_argument("-o", "--output", default="project_code.txt",
#                         help="Имя выходного файла")
#     parser.add_argument("-r", "--root-dir", default=".",
#                         help="Корневая директория проекта")
#     parser.add_argument("-e", "--extensions", nargs="+",
#                         help="Расширения файлов для включения")
#     parser.add_argument("--exclude-dirs", nargs="+", default=[],
#                         help="Дополнительные директории для исключения")
#     parser.add_argument("--min-size", type=int, default=0,
#                         help="Минимальный размер файла в байтах")
#     parser.add_argument("--line-numbers", action="store_true",
#                         help="Добавить нумерацию строк")
#
#     args = parser.parse_args()
#     collect_code(args)
#
#
# if __name__ == "__main__":
#     main()