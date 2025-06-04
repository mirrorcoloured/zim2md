import os
import sys
import re
from pathlib import Path
import shutil
import datetime
import json

from tqdm import tqdm
from PIL import Image


def __compatible(lines):
    """Return True iff the first two lines of a file allute to it being
    convertible or not."""
    if len(lines) < 2:
        return False
    if not re.fullmatch(r"^Content-Type: text/x-zim-wiki$", lines[0].strip()):
        return False
    if not re.fullmatch(r"^Wiki-Format: zim 0\.[0-6]$", lines[1].strip()) is not None:
        return False
    return True


def compatible(path=None, infile=None, lines=None):
    """Return True iff the given path points to a Zim Wiki file."""
    if path is not None:
        with open(path, "r", encoding="utf-8") as _f:
            return __compatible(_f.readlines()[:4])
    elif infile is not None:
        return __compatible(infile.readlines()[:4])
    elif lines is not None:
        return __compatible(lines[:4])
    return True


def make_unique_string(existing_names: list[str], requested_name: str) -> str:
    """Given a list of strings and a new string, returns a string that
    does not already exist in the list by adding or incrementing
    a final number in the filename."""
    proposed_filename = requested_name
    while proposed_filename in existing_names:
        final_digits = re.findall("(.*?)(\d+)(\..+)", proposed_filename)
        if final_digits:
            previous_digits = final_digits[0][1]
            new_digits = str(int(previous_digits) + 1)
            proposed_filename = "".join(
                [
                    final_digits[0][0],
                    new_digits,
                    final_digits[0][2],
                ]
            )
        else:
            fname, extension = os.path.splitext(proposed_filename)
            proposed_filename = f"{fname} 1{extension}"
    return proposed_filename


def make_unique_filename(directory: Path, requested_filename: str) -> str:
    """Given a filename and directory, returns a valid filename that
    does not already exist in the directory by adding or incrementing
    a final number in the filename."""
    dir_files = os.listdir(directory)
    return make_unique_string(dir_files, requested_filename)


def map_zim_dir_to_obsidian_dir(
    zim_dir: Path,
    obs_dir: Path,
    ignore_extensions: list[str] = [".ini"],
    use_folder_notes: bool = True,
    use_global_attachments: bool = True,
    global_attachments_relative_path: Path = Path("attachments"),
):
    """Scans a zim-wiki directory and creates mappings for folders, note files, and other
    files to an obsidian file structure."""
    folder_map = {}
    note_map = {}
    file_map = {}

    total_iterations = 0
    for walkroot, folders, files in os.walk(zim_dir):
        total_iterations += 1

    for walkroot, folders, files in tqdm(
        os.walk(zim_dir),
        desc="Mapping zim directory",
        total=total_iterations,
    ):
        walkroot = Path(walkroot)
        relroot = "" if walkroot == Path(zim_dir) else walkroot.relative_to(zim_dir)
        for folder in folders:
            c_folderpath_old = zim_dir.joinpath(relroot, folder)
            c_folderpath_new = obs_dir.joinpath(relroot, folder)
            folder_map[c_folderpath_old] = c_folderpath_new
        for file in files:
            c_filepath_old = zim_dir.joinpath(relroot, file)
            if os.path.splitext(file)[1] == ".txt" and compatible(c_filepath_old):
                potential_folder_path = obs_dir.joinpath(
                    relroot, os.path.splitext(file)[0]
                )
                if use_folder_notes and potential_folder_path in folder_map.values():
                    # move inside folder with same name
                    c_filepath_new = potential_folder_path.joinpath(file)
                else:
                    c_filepath_new = obs_dir.joinpath(relroot, file)

                # rename text to markdown
                c_filepath_new = c_filepath_new.with_suffix(".md")

                note_map[c_filepath_old] = c_filepath_new
            else:
                if os.path.splitext(file)[1] in ignore_extensions:
                    continue
                if use_global_attachments:
                    proposed_name = obs_dir.joinpath(
                        global_attachments_relative_path, file
                    )
                    unique_filename = Path(
                        make_unique_string(
                            [str(s) for s in file_map.values()], str(proposed_name)
                        )
                    )
                    file_map[c_filepath_old] = unique_filename
                else:
                    c_filepath_new = obs_dir.joinpath(relroot, file)
                    file_map[c_filepath_old] = c_filepath_new

    return folder_map, note_map, file_map


def zim_filepath_to_title(filepath: Path) -> str:
    """Given a filepath to a zim .txt, get the title of the page

    Ex.
    'G:\\My Drive\\myethos\\subfolder\\somewhere\\armadillo.txt',
    ->
    'armadillo'
    """
    return os.path.splitext(os.path.basename(filepath))[0].replace("_", " ")


def zim_filepath_to_titlepath(filepath: Path, zim_dir: Path) -> str:
    """Given a filepath to a zim.txt and notebook directory, get the relative
    title to the page.

    Ex.
    'G:\\My Drive\\myethos\\subfolder\\somewhere\\armadillo.txt',
    'G:\\My Drive\\myethos'
    ->
    'subfolder\\somewhere\\armadillo'
    """
    return os.path.splitext(os.path.relpath(filepath, zim_dir))[0].replace("_", " ")


def translate_file(
    zim_dir: Path,
    obs_dir: Path,
    old_filepath: Path,
    note_map: dict[Path, Path],
    file_map: dict[Path, Path],
    use_folder_notes: bool,
    use_global_attachments: bool,
    global_attachments_relative_path: Path,
) -> list[str]:
    """Translate a zim file into an Obsidian note."""

    with open(old_filepath, "r", encoding="utf-8") as _f:
        lines = _f.readlines()

    # remove file format headers
    lines = lines[4:]

    # ignore duplicate title text
    title = zim_filepath_to_title(old_filepath)
    topline = re.findall("====== (.*) ======", lines[0])
    if topline and topline[0].replace("_", " ") == title:
        lines = lines[1:]

    i = -1
    while i < len(lines) - 1:
        i += 1
        line = lines[i]

        if line.startswith("{{{code:"):
            # code blocks
            langtag = re.findall('.+lang="(.+)" ', line)
            if langtag:
                lang = langtag[0]
                if lang == "python3":
                    lang = "python"
            else:
                lang = ""
            lines[i] = f"```{lang}\n"
            j = 0
            subline = lines[i + j]
            while not subline.startswith("}}}"):
                j += 1
                subline = lines[i + j]
            lines[i + j] = "```\n"
            i += j + 1
            continue
        else:
            # general line translation
            try:
                line = translate_line(
                    line,
                    zim_dir,
                    obs_dir,
                    old_filepath,
                    note_map,
                    file_map,
                    use_folder_notes,
                    use_global_attachments,
                    global_attachments_relative_path,
                )
            except Exception as e:
                print(f"Error in file: `{old_filepath}` in line: `{line}`")
                raise e
            lines[i] = line

    return lines


def translate_line(
    line: str,
    zim_dir: Path,
    obs_dir: Path,
    old_filepath: Path,
    note_map: dict[Path, Path],
    file_map: dict[Path, Path],
    use_folder_notes: bool,
    use_global_attachments: bool,
    global_attachments_relative_path: Path,
) -> str:

    title = zim_filepath_to_title(old_filepath)

    # Headings
    line = re.sub(r"^(=+)([^=]+)=+$", r"\g<1>\g<2>", line)  # removes tailing '='
    line = re.sub(r"^======", "#", line)
    line = re.sub(r"^=====", "##", line)
    line = re.sub(r"^====", "###", line)
    line = re.sub(r"^===", "####", line)
    line = re.sub(r"^==", "#####", line)
    line = re.sub(r"^=", "######", line)

    # Dates
    line = re.sub(
        r"\[d:(\d{4}-\d{,2}-\d{,2})](.+)$", r"\g<2>\nDEADLINE: <\g<1> Day>", line
    )
    line = re.sub(
        r"\[d:(\d{,2})\.(\d{,2})\.(\d{4})](.+)$",
        r"\g<4>\nDEADLINE: <\g<3>-\g<2>-\g<1> Day>",
        line,
    )  # central European date format!
    line = re.sub(
        r"\[d:(\d{,2})/(\d{,2})/(\d{4})](.+)$",
        r"\g<4>\nDEADLINE: <\g<3>-\g<1>-\g<2> Day>",
        line,
    )  # American dates!
    line = re.sub(
        r"\[d:(\d{,2}).(\d{,2}).\](.+)$",
        r"\g<3>\nDEADLINE: <" + str(datetime.date.today().year) + r"-\g<2>-\g<1> Day>",
        line,
    )

    # Hyperlink text [[ ]]
    for bracketed_link, internal in re.findall(
        r"([\[]{2}(.+?\|?[^\]]+?)[\]]{2})", line
    ):
        target = ""
        absolute = False
        # stars with nothing, or [[file:///]] or [[+]] or [[:]] or [[wp?]] or [[./]] or [[.\\]]
        if "|" in internal:
            target, display = internal.split("|")
        else:
            target = display = internal

        # replace wikipedia shortcuts with full links
        if target.startswith("wp?"):
            display = target[3:]
            target = target.replace("wp?", "https://wikipedia.org/wiki/").replace(
                " ", "_"
            )

        page_path = zim_filepath_to_titlepath(old_filepath, zim_dir)

        if target.startswith("http"):
            pass
        elif target.startswith("file:///"):
            target = target[8:]
            try:
                zim_rel_path = Path(target).relative_to(zim_dir)
                raise Exception(
                    f"Absolute path `{target}` is actually inside zim folder in line `{line}`"
                )
            except ValueError:
                # not a related path, use as absolute
                absolute = True
        elif target.startswith("./") or target.startswith(".\\"):
            target = target[2:]
            if display.startswith("./") or display.startswith(".\\"):
                display = display[2:]
            absolute = False
            zim_abs_path = zim_dir.joinpath(page_path, target)
            obs_abs_path = file_map[zim_abs_path]
            if use_global_attachments:
                attachment_dir = obs_dir.joinpath(global_attachments_relative_path)
                obs_rel_path = obs_abs_path.relative_to(attachment_dir)
            else:
                obs_rel_path = obs_abs_path.relative_to(obs_dir)
            target = str(obs_rel_path)
        else:
            # modify relative links
            # TODO found one edge case where linking to [[b]] with multiple b pages chose the wrong one,
            # maybe should be more explicit in referencing the most immediate page from the current leaf page?
            absolute = False
            if target.startswith("+"):
                target = page_path + ":" + target[1:]
            if target.startswith(":"):
                target = target[target[1:].find(":") + 2 :]
            target = target.replace(":", "\\")

        # if using folder notes, point in one level to the page
        if use_folder_notes and zim_dir.joinpath(target).is_dir():
            target = os.path.join(target, os.path.split(target)[-1])
        
        # check for underscore weirdness
        if zim_dir.joinpath(target).with_suffix(".txt") not in note_map:
            under_target = target.replace(" ", "_")
            if zim_dir.joinpath(under_target).with_suffix(".txt") in note_map:
                target = under_target

        # replace backslash with forward slash for obsidian links
        target = target.replace("\\", "/")

        # replace link structure
        # Valid link formats:
        # [[0Plots/Rich people|Rich people]]      [[target|label]]
        # [Rich people](0Plots/Rich%20people)     [label](target.replace(" ", "%20"))
        # [Rich people](<0Plots/Rich people>)     [label](<target>)
        if (not target == display) or absolute:
            if " " in target:
                line = line.replace(bracketed_link, f"[{display}](<{target}>)", 1)
            else:
                line = line.replace(bracketed_link, f"[{display}]({target})", 1)
        else:
            line = line.replace(bracketed_link, f"[[{target}]]", 1)

    # File object links (usually images) {{ }}
    for bracketed_link, internal in re.findall(
        r"([\{]{2}(.+?\|?[^\]]+?)[\}]{2})", line
    ):
        target = ""
        absolute = False
        # starts with {{file:///}} or {{./}} or {{.\\}}
        # may have properties like {{?width=100}}
        options = None
        if "?" in internal:
            target, options = internal.split("?")
        else:
            target = internal

        page_path = zim_filepath_to_titlepath(old_filepath, zim_dir)

        if target.startswith("file:///"):
            # TODO when absolute references exist obsidian randomly enters newlines?
            # maybe copy file into folder and link to that instead?

            # ![](C:/Users/Mirro/Downloads/5096196.png)
            target = target[8:]
            try:
                zim_rel_path = Path(target).relative_to(zim_dir)
                raise Exception(
                    f"Absolute path `{target}` is actually inside zim folder in line `{line}`"
                )
            except ValueError:
                # not a related path, use as absolute
                zim_abs_path = Path(target)
                absolute = True

        if target.startswith(".\\") or target.startswith("./"):
            absolute = False
            target = target[2:]

            local_folder = old_filepath.relative_to(zim_dir).with_suffix("")
            zim_abs_path = zim_dir.joinpath(local_folder, target)
            obs_abs_path = file_map[zim_abs_path]

            if use_global_attachments:
                attachment_dir = obs_dir.joinpath(global_attachments_relative_path)
                obs_rel_path = obs_abs_path.relative_to(attachment_dir)
            else:
                obs_rel_path = obs_abs_path.relative_to(obs_dir)

            target = str(obs_rel_path)

        if options:
            options_dict = dict([x.split("=") for x in options.split("&")])
            for key, value in options_dict.items():
                if key in ["height", "width"]:
                    try:
                        with Image.open(zim_abs_path) as img:
                            width, height = img.size
                        if key == "height":
                            x_height = int(options_dict["height"])
                            x_width = int(int(options_dict["height"]) / height * width)
                        else:
                            x_width = int(options_dict["width"])
                            x_height = int(int(options_dict["width"]) / width * height)
                        target = f"{target}|{x_width}x{x_height}"
                    except Exception as e:
                        print(f"Couldn't read width/height from image `{zim_abs_path}` referenced by file `{old_filepath}`")
                elif key == "type":
                    pass
                else:
                    print(f"Unknown option `{key}` in line `{line}` in file `{old_filepath}`")

        if absolute:
            line = line.replace(bracketed_link, f"![](file:///{target})", 1)
        else:
            line = line.replace(bracketed_link, f"![[{target}]]", 1)

    # Lists
    line = re.sub(r"^(\s*)\[\*\]", r"\g<1>- [*]", line, count=1)
    line = re.sub(r"^(\s*)\[x\]", r"\g<1>- [x]", line, count=1)
    line = re.sub(r"^(\s*)\[>\]", r"\g<1>- [>]", line, count=1)
    line = re.sub(r"^(\s*)\[ \]", r"\g<1>- [ ]", line, count=1)
    # TODO indented list elements without dots or checkboxes

    # @tags and +SubPageReferences
    line = re.sub(r"^@(\S+)", r"#\g<1>", line)
    line = re.sub(r"\s+@(\S+)", r"#\g<1>", line)
    line = re.sub(r"\[\[\+(\S+?)\]\]", r"[[\g<1>]]", line)

    # italics
    line = re.sub(r"//(.+?)//", r"*\g<1>*", line)

    # rich text formatting?
    line = re.sub(r"_\{(.+?)\}", r"<sub>\g<1></sub>", line)
    line = re.sub(r"\^\{(.+?)\}", r"<sup>\g<1></sup>", line)
    line = re.sub(r"~~(.+?)~~", r"~~\g<1>~~", line)
    line = re.sub(r"(!?<=:)//([^:]+?)//", r"*\g<1>*", line)
    line = re.sub(r"\*\*(.+?)\*\*", r"**\g<1>**", line)
    line = re.sub(r"__(.+?)__", r"==\g<1>==", line)

    # horizontal line
    line = re.sub(r"--------------------", r"\n---", line)

    # footnotes, unused and messes with links like `![](C:/Users/Mirro/Downloads/5096196.png|300x300)`
    # line = re.sub(r"(?!<=\[)\[([0-9]{,4})\](?!=\])", r"[^\g<1>]", line)

    # # Images with parameters
    # line = re.sub(r"{{./(.+?)(?:\?.+)}}", rf"![[{title}/\g<1>]]", line)
    # line = re.sub(r"{{.\\(.+?)(?:\?.+)}}", rf"![[{title}/\g<1>]]", line)

    # # Images without parameters
    # line = re.sub(r"{{./(.+?)}}", rf"![[{title}/\g<1>]]", line)
    # line = re.sub(r"{{.\\(.+?)}}", rf"![[{title}/\g<1>]]", line)

    # Old image lines
    # line = re.sub(r"{{(.+?)}}", r"![[\g<1>]]", line)
    # line = re.sub(r"{{(.+?)|(.+?)}}", r"![[\g<1>]]", line)

    return line


def migrate_zim_to_obsidian(
    zim_dir: Path,
    obs_dir: Path,
    use_folder_notes: bool,
    use_global_attachments: bool,
    global_attachments_relative_path: Path = Path("attachments"),
):

    # scan folder and make maps of file changes
    folder_map, note_map, file_map = map_zim_dir_to_obsidian_dir(
        zim_dir,
        obs_dir,
        use_folder_notes=use_folder_notes,
        use_global_attachments=use_global_attachments,
        global_attachments_relative_path=global_attachments_relative_path,
    )

    with open('folder_map.json', 'w', encoding="utf-8") as f:
        json.dump({str(k).replace("\\", "/").replace(str(zim_dir).replace("\\", "/"), "ℤ"): str(v).replace("\\", "/").replace(str(obs_dir).replace("\\", "/"), "𝕆") for k, v in folder_map.items()}, f, indent=2, ensure_ascii=False)
    with open('note_map.json', 'w', encoding="utf-8") as f:
        json.dump({str(k).replace("\\", "/").replace(str(zim_dir).replace("\\", "/"), "ℤ"): str(v).replace("\\", "/").replace(str(obs_dir).replace("\\", "/"), "𝕆") for k, v in note_map.items()}, f, indent=2, ensure_ascii=False)
    with open('file_map.json', 'w', encoding="utf-8") as f:
        json.dump({str(k).replace("\\", "/").replace(str(zim_dir).replace("\\", "/"), "ℤ"): str(v).replace("\\", "/").replace(str(obs_dir).replace("\\", "/"), "𝕆") for k, v in file_map.items()}, f, indent=2, ensure_ascii=False)

    # re-create folder structure
    for old_folder, new_folder in tqdm(folder_map.items(), desc="Creating folder structure"):
        if not os.path.exists(new_folder):
            os.makedirs(new_folder, exist_ok=True)

    # move non-note files
    if use_global_attachments:
        os.makedirs(obs_dir.joinpath(global_attachments_relative_path), exist_ok=True)
    for old_filepath, new_filepath in tqdm(file_map.items(), desc="Copying non-note files"):
        shutil.copy(old_filepath, new_filepath)

    # translate and move note files
    for old_filepath, new_filepath in tqdm(note_map.items(), desc="Translating and moving notes"):

        new_content = translate_file(
            zim_dir,
            obs_dir,
            old_filepath,
            note_map,
            file_map,
            use_folder_notes,
            use_global_attachments,
            global_attachments_relative_path,
        )

        with open(new_filepath, "w", encoding="utf-8") as f:
            f.write("".join(new_content))

    return folder_map, note_map, file_map


def test_aaatest():
    zim_dir = Path("G:/My Drive/myethos/aaatest")
    obs_dir = Path("C:/Users/Mirro/Desktop/testethos")
    use_folder_notes = True
    use_global_attachments = True
    global_attachments_relative_path = Path("attachments")

    folder_map, note_map, file_map = migrate_zim_to_obsidian(
        zim_dir=zim_dir,
        obs_dir=obs_dir,
        use_folder_notes=use_folder_notes,
        use_global_attachments=use_global_attachments,
        global_attachments_relative_path=global_attachments_relative_path,
    )

    # folders
    assert folder_map[Path(f"{zim_dir}\\Bumblebee")] == Path(f"{obs_dir}\\Bumblebee")
    assert folder_map[Path(f"{zim_dir}\\capybara")] == Path(f"{obs_dir}\\capybara")
    assert folder_map[Path(f"{zim_dir}\\Bumblebee\\Buzzy")] == Path(
        f"{obs_dir}\\Bumblebee\\Buzzy"
    )
    assert folder_map[Path(f"{zim_dir}\\Bumblebee\\honey")] == Path(
        f"{obs_dir}\\Bumblebee\\honey"
    )

    # note files
    assert note_map[Path(f"{zim_dir}\\armadillo.txt")] == Path(
        f"{obs_dir}\\armadillo.md"
    )
    assert note_map[Path(f"{zim_dir}\\Bumblebee.txt")] == Path(
        f"{obs_dir}\\Bumblebee\\Bumblebee.md"
    )
    assert note_map[Path(f"{zim_dir}\\capybara.txt")] == Path(
        f"{obs_dir}\\capybara\\capybara.md"
    )
    assert note_map[Path(f"{zim_dir}\\Bumblebee\\Buzzy.txt")] == Path(
        f"{obs_dir}\\Bumblebee\\Buzzy\\Buzzy.md"
    )
    assert note_map[Path(f"{zim_dir}\\Bumblebee\\honey.txt")] == Path(
        f"{obs_dir}\\Bumblebee\\honey\\honey.md"
    )
    assert note_map[Path(f"{zim_dir}\\capybara\\honey.txt")] == Path(
        f"{obs_dir}\\capybara\\honey.md"
    )

    # other files
    assert file_map[Path(f"{zim_dir}\\Bumblebee\\Buzzy\\pasted_image.png")] == Path(
        f"{obs_dir}\\attachments\\pasted_image.png"
    )
    assert file_map[Path(f"{zim_dir}\\Bumblebee\\honey\\pasted_image.png")] == Path(
        f"{obs_dir}\\attachments\\pasted_image 1.png"
    )
    assert file_map[Path(f"{zim_dir}\\capybara\\pasted_image.png")] == Path(
        f"{obs_dir}\\attachments\\pasted_image 2.png"
    )
    assert file_map[Path(f"{zim_dir}\\capybara\\139-item-catch.mp3")] == Path(
        f"{obs_dir}\\attachments\\139-item-catch.mp3"
    )


if __name__ == "__main__":
    # sys.argv
    if False:
        zim_dir = Path("G:/My Drive/myethos")
        obs_dir = Path("C:/Users/Mirro/Desktop/testethos")
        use_folder_notes = True
        use_global_attachments = True
        global_attachments_relative_path = Path("attachments")

        folder_map, note_map, file_map = migrate_zim_to_obsidian(
            zim_dir=zim_dir,
            obs_dir=obs_dir,
            use_folder_notes=use_folder_notes,
            use_global_attachments=use_global_attachments,
            global_attachments_relative_path=global_attachments_relative_path,
        )
