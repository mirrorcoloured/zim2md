#!/usr/bin/env python3

"""
Converts [Zim Desktop Wiki](https://zim-wiki.org) to Markdown

Usage:
    python zim2md.py <input.file> <output.file>
"""

USE_FOLDER_NOTES = True

import os
from re import sub, fullmatch, findall
from pathlib import Path
from shutil import copy2
from datetime import datetime
from typing import List
import sys

def __compatible(lines):
    """Return True iff the first two lines of a file allute to it being
    convertible or not."""
    if len(lines) < 2:
        return False
    if not fullmatch(r"^Content-Type: text/x-zim-wiki$", lines[0].strip()):
        return False
    if not fullmatch(r"^Wiki-Format: zim 0\.[0-6]$", lines[1].strip()) is not None:
        return False
    return True


def compatible(path=None, infile=None, lines=None):
    """Return True iff the given path points to a Zim Wiki file."""
    if path is not None:
        with open(path, "r") as _f:
            return __compatible(_f.readlines()[:4])
    elif infile is not None:
        return __compatible(infile.readlines()[:4])
    elif lines is not None:
        return __compatible(lines[:4])
    return True

# TODO make test file that has everything

def translate(text: List[str], path:str="", nbpath:str="") -> List[str]:
    """Discards the first four lines. All other lines are converted."""
    # The first 4 lines usually contain file format info.
    text = text[4:]
    headline_nr = 0
    current_ind = 0
    title = os.path.splitext(os.path.basename(path))[0].replace("_", " ")
    relpath = "/".join(str(os.path.relpath(path, nbpath)).split(os.sep)[:-1])

    # ignore duplicate title text
    topline = findall("====== (.*) ======", text[0])
    if topline and topline[0].replace("_", " ") == title:
        text = text[1:]

    i = 0
    while i < len(text):
        line = text[i]

        # Head lines
        line = sub(r"^(=+)([^=]+)=+$", r"\g<1>\g<2>", line) # removes tailing '='
        line = sub(r"^======", "#", line)
        line = sub(r"^=====", "##", line)
        line = sub(r"^====", "###", line)
        line = sub(r"^===", "####", line)
        line = sub(r"^==", "#####", line)
        line = sub(r"^=", "######", line)

        # Dates
        line = sub(r"\[d:(\d{4}-\d{,2}-\d{,2})](.+)$", r"\g<2>\nDEADLINE: <\g<1> Day>", line)
        line = sub(r"\[d:(\d{,2})\.(\d{,2})\.(\d{4})](.+)$", r"\g<4>\nDEADLINE: <\g<3>-\g<2>-\g<1> Day>", line) # central European date format!
        line = sub(r"\[d:(\d{,2})/(\d{,2})/(\d{4})](.+)$", r"\g<4>\nDEADLINE: <\g<3>-\g<1>-\g<2> Day>", line) # American dates!
        line = sub(r"\[d:(\d{,2}).(\d{,2}).\](.+)$",
                r"\g<3>\nDEADLINE: <" + str(datetime.now().year) + r"-\g<2>-\g<1> Day>",
                line)

        # Links
        for link in findall(r"\[\[:.+?\]\]", line):
            target = link[2:-2]
            # TODO relative to current file
            target = target.replace(":", "/")
            line = line.replace(link, f"[[{target}]]", 1)
        
        # not sure why they were excluding links starting with +
        # for link in findall(r"\[\[[^+]+?\|?[^\]]+?\]\]", line):
        for link in findall(r"\[\[.+?\|?[^\]]+?\]\]", line):
            label, target = None, None
            tokens = link[2:-2].split("|")

            if len(tokens) > 2:
                # probably not a link.
                continue

            if len(tokens) == 2:
                target, label = tokens
            else:
                label = tokens[0]
                target = tokens[0]

            target = sub(r"^~", Path.home().as_uri(), target)

            if not target.startswith("http://") \
                    and not target.startswith("https://") \
                    and not target.startswith("file://"):
                # target = target.replace(" ", "_")
                target = target.replace(":", "/")
                target = target.replace("+", f"{title}/")

            # Valid link formats:
            # [[0Plots/Rich people|Rich people]]      [[target|label]]
            # [Rich people](0Plots/Rich%20people)     [label](target.replace(" ", "%20"))
            # [Rich people](<0Plots/Rich people>)     [label](<target>)
            if not target == label:
                if " " in target:
                    line = line.replace(link, f"[{label}](<{target}>)", 1)
                else:
                    line = line.replace(link, f"[{label}]({target})", 1)
            else:
                line = line.replace(link, f"[[{target}]]", 1)
        line = sub(r"(file://\S+)", r"[\g<1>](\g<1>)", line)

        # Lists
        line = sub(r"^(\s*)\[\*\]", r"\g<1>- [*]", line, count=1)
        line = sub(r"^(\s*)\[x\]", r"\g<1>- [x]", line, count=1)
        line = sub(r"^(\s*)\[>\]", r"\g<1>- [>]", line, count=1)
        line = sub(r"^(\s*)\[ \]", r"\g<1>- [ ]", line, count=1)
        # TODO indented list elements without dots or checkboxes

        # @tags and +SubPageReferences
        line = sub(r"^@(\S+)", r"#\g<1>", line)
        line = sub(r"\s+@(\S+)", r"#\g<1>", line)
        line = sub(r"\[\[\+(\S+?)\]\]", r"[[\g<1>]]", line)

        # italics
        line = sub(r"//(.+?)//", r"*\g<1>*", line)
        
        # rich text formatting?
        line = sub(r"_\{(.+?)\}", r"<sub>\g<1></sub>", line)
        line = sub(r"\^\{(.+?)\}", r"<sup>\g<1></sup>", line)
        line = sub(r"~~(.+?)~~", r"~~\g<1>~~", line)
        line = sub(r"(!?<=:)//([^:]+?)//", r"*\g<1>*", line)
        line = sub(r"\*\*(.+?)\*\*", r"**\g<1>**", line)
        line = sub(r"__(.+?)__", r"==\g<1>==", line)

        # horizontal line
        line = sub(r"--------------------", r"\n---", line)

        # footnotes
        line = sub(r"(?!<=\[)\[([0-9]{,4})\](?!=\])", r"[^\g<1>]", line)

        # Images with parameters
        line = sub(r"{{./(.+?)(?:\?.+)}}", rf"![[{title}/\g<1>]]", line)
        line = sub(r"{{.\\(.+?)(?:\?.+)}}", rf"![[{title}/\g<1>]]", line)
        
        # Images without parameters
        line = sub(r"{{./(.+?)}}", rf"![[{title}/\g<1>]]", line)
        line = sub(r"{{.\\(.+?)}}", rf"![[{title}/\g<1>]]", line)
        
        # Old image lines
        # line = sub(r"{{(.+?)}}", r"![[\g<1>]]", line)
        # line = sub(r"{{(.+?)|(.+?)}}", r"![[\g<1>]]", line)

        # Code blocks
        if line.startswith("{{{code:"):
            langtag = findall('.+lang="(.+)" ', line)
            if langtag:
                lang = langtag[0]
                if lang == "python3":
                    lang = "python"
            else:
                lang = ""
            text[i] = f"```{lang}\n"
            j = 0
            subline = text[i + j]
            while not subline.startswith("}}}"):
                j += 1
                subline = text[i + j]
            text[i + j] = "```\n"
            i += j + 1
            continue

        text[i] = line
        i += 1

    # TODO more features
    return text


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        ls = sys.stdin.readlines()
        if compatible(lines=ls):
            sys.stdout.writelines(translate(text=ls))
        else:
            sys.stderr.writelines(["FATAL: Incompatible file.\n"])
            sys.exit(1)
    else:
        _path = os.path.normpath(sys.argv[1])
        _newpath = os.path.normpath(sys.argv[2])

        os.makedirs(_newpath, exist_ok=True)

        for olddir, folders, files in os.walk(_path):

            if olddir != _path:
                relpath = os.path.relpath(olddir, _path)
            else:
                relpath = ""

            for folder in folders:
                os.makedirs(os.path.join(
                    _newpath,
                    relpath.replace("_", " "),
                    folder.replace("_", " "),
                ), exist_ok=True)

            for file in files:

                # temp google drive workaround
                if os.path.splitext(file)[1].lower() in [".gform", ".gsheet"]:
                    continue

                old_fp = os.path.join(olddir, file)

                if os.path.splitext(file)[1].lower() == ".txt":
                    new_folder = os.path.join(
                        _newpath,
                        relpath.replace("_", " "),
                    )
                    new_fileid = os.path.splitext(file.replace("_", " "))[0]
                    new_filename = new_fileid + ".md"
                    if USE_FOLDER_NOTES and os.path.isdir(os.path.join(new_folder, new_fileid)):
                        new_fp = os.path.join(
                            new_folder,
                            new_fileid,
                            new_filename
                        )
                    else:
                        new_fp = os.path.join(
                            new_folder,
                            new_filename
                        )

                    print(f"Translating {old_fp} to {new_fp}")
                    with open(old_fp, 'r', encoding="utf-8") as _f:
                        lines = _f.readlines()
                    lines = translate(lines, old_fp, new_fp)
                    with open(new_fp, 'w', encoding="utf-8") as _o:
                        _o.writelines(lines)
                else:
                    new_fp = os.path.join(
                        _newpath,
                        relpath.replace("_", " "),
                        file,
                    )
                    print(f"Copying {old_fp} to {new_fp}")
                    copy2(old_fp, new_fp)
