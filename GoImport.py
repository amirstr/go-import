import sublime
import sublime_plugin
import re
import os

parantheseImportRegex = r"import.*\((.|\n)*?\)";
qouteImportRegex = r"import.*\"(.*)\"";

class GoImportCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if ('Go' not in self.view.syntax().name): return

        words = self.filter_imported_words(self.get_words());
        words = list(set(words));

        if len(words) == 0: sublime.status_message('GoImport: already imported.'); return;

        words = self.get_full_word_names(words);

        if (len(words) == 0): sublime.status_message("GoImport: keyword not found"); return

        self.import_words(edit, words);

    # get import key words by active cursors
    def get_words(self):
        words = [];

        for cursor in self.view.sel():
            word = self.view.substr(self.view.word(cursor)).strip();
            if (bool(re.match("^[a-zA-Z0-9]+$", word))): words.append(word);

        return words;

    # removes words that are not in /usr/lib/go/src/...
    # removed words that are not directory in opened directory
    # removed words that are not installed
    # e.g, utf8 to unicode/utf8 based on /usr/lib/go/src/...
    def get_full_word_names(self, words):
        full_word_names = [];
        currentProjectPath = self.view.window().extract_variables()['folder'];
        searchInPaths = [
            currentProjectPath,
            '/usr/lib/go/src',
            '~/go/pkg/mod/cache/download',
        ];

        for w in words:
            found = False;

            for path in searchInPaths:
                path = os.path.expanduser(path);

                for l in os.listdir(path):
                    if not os.path.isdir(path.rstrip('/')+'/'+l): continue
                    if w == l:
                        # including project module name itself
                        if currentProjectPath in path:
                            moduleName = get_project_module_name(currentProjectPath)
                            if moduleName: w = moduleName+'/'+w

                        full_word_names.append(w); found = True; break;

                if found: continue;

                for l in os.walk(path):
                    fullPath = l
                    if '/testdata' in l[0]: continue
                    l = l[0].replace(path.rstrip('/')+'/', '')
                    l = re.sub('@.*$', '', l)

                    if w == l.split('/')[-1]:
                        # including project module name itself
                        if currentProjectPath in fullPath[0]:
                            moduleName = get_project_module_name(currentProjectPath)
                            if moduleName: l = moduleName+'/'+l

                        full_word_names.append(l); break;

        return full_word_names;

    # removes words that are already imported.
    def filter_imported_words(self, words):
        if (not has_import_key_word(self.view)):
            return words;

        filteredWords = [];
        imported_words = get_imported_words(self.view);
        for w in words:
            isAlreadyImported = False;

            for iw in imported_words:
                if w != iw.split('/')[-1]: isAlreadyImported = isAlreadyImported or False;
                else: isAlreadyImported = True;

            if not isAlreadyImported: filteredWords.append(w)

        return filteredWords;

    # add given words to imports
    def import_words(self, edit, words):
        if len(words) == 0: return;

        if has_import_key_word(self.view): words += get_imported_words(self.view)

        page_imports(self.view, edit, words);

        sublime.status_message('GoImport: imported!');


class GoImportEraseUnusedCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if ('Go' not in self.view.syntax().name): return

        importedWords = get_imported_words(self.view);
        unusedWords = self.get_unused_words(importedWords);

        if len(unusedWords) == 0: sublime.status_message('GoImport: no unused import found.'); return;

        self.erase_imports(edit, unusedWords);

    # removes import keywords
    def erase_imports(self, edit, unusedWords):
        if len(unusedWords) == 0: return;

        remainedWords = [];
        imported_words = get_imported_words(self.view)

        for iw in imported_words:
            if iw not in unusedWords: remainedWords.append(iw)

        page_imports(self.view, edit, remainedWords);

        sublime.status_message('GoImport: erased!')

    # returns unused import keywords in page
    def get_unused_words(self, words):
        unusedWords = [];

        for fullWord in words:
            w = fullWord;
            if '/' in w: w = fullWord.split('/')[-1];
            regions = self.view.find_all(w+'\.', 0);

            if len(regions) == 0: unusedWords.append(fullWord); continue;

            found = False;

            for region in regions:
                line = self.view.substr(self.view.line(region));
                if '//' in line: found = found or False;
                else: found = True;

            if not found: unusedWords.append(fullWord)

        return unusedWords;

# words that page imports
def page_imports(view, edit, words):
    words = list(set(words));
    packageViewRegion = view.find('package.*$', 0);
    importString = "";

    if not has_import_key_word(view):
        if len(words) == 0: return;
        replaceViewRegion = packageViewRegion;
        importString = view.substr(packageViewRegion)+"\n\n";

        if len(words) == 1: importString+="import \""+words[0]+"\""
        else:
            importString += "import ("
            for w in words: importString+="\n\t\""+w+"\""
            importString += "\n)"

        view.replace(edit, replaceViewRegion, importString);
        return;

    replaceViewRegion = view.find(qouteImportRegex, 0) or view.find(parantheseImportRegex, 0);
    importString += "import ("
    for w in words: importString+="\n\t\""+w+"\""
    importString += "\n)"

    if len(words) == 0: view.replace(edit, replaceViewRegion, "");
    if len(words) == 0: view.replace(edit, view.find('package.*\n\n', 0), view.substr(packageViewRegion)); return;

    view.replace(edit, replaceViewRegion, importString);

# get project module name based on go.mod
def get_project_module_name(projectPath):
    path = os.path.expanduser(projectPath);
    goModPath = path+'/'+'go.mod';

    if not (os.path.exists(goModPath) and os.path.isfile(goModPath)): return ''

    with open(goModPath, 'r') as f:
        line = f.readline();
        if bool(re.match("module.*", line)):
            return re.findall("module.*", line)[0].split(' ')[-1]

    return '';

# get imported words of page
def get_imported_words(view):
    if not has_import_key_word(view): return [];

    parantheseImportRegion = view.find(parantheseImportRegex, 0);
    qouteImportRegion = view.find(qouteImportRegex, 0);

    # if has import with parantheses ()
    if bool(parantheseImportRegion):
        importString = view.substr(parantheseImportRegion);
    # if has import inside ""
    elif bool(qouteImportRegion):
        importString = view.substr(qouteImportRegion)

    words = re.findall(r"[a-zA-Z0-9\/\.]+", importString);
    if 'import' in words: words.remove('import');

    return words;

# determine page has any importes
def has_import_key_word(view):
    return bool(view.find('import', 0))
