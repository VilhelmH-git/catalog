# catalog

`catalog.json` lists everything **BoomerHubb** can install: the team's MSIX apps and the
CAD/BIM plugins. BoomerHubb downloads this one file (from `raw.githubusercontent.com`, not the
GitHub API, so a whole office behind one IP never meets the API's 60 requests an hour), compares
each entry's `version` with what is installed, and installs from the URLs in it.

Each product keeps publishing to its own public `<Product>-releases` repository. Its release
script then calls `set_entry.py` (in the private claude-kit, `tools/catalog/`), which points the
product's entry at the new release. A release stays one step.

## Adding a product

1. Make sure the product publishes to a **public** releases repository, and that its release
   passes the release gate (claude-kit `tools/release-scan`): everything listed here is public.
2. Add its entry to `catalog.json` by hand, with the fields marked *by hand* below and a
   `pattern` for every file. Leave `version` empty. Commit and push.
3. Fill in the rest from its latest release:

   ```
   python <claude-kit>/tools/catalog/set_entry.py --id <id> --repo VilhelmH-git/<Product>-releases [--cert-thumbprint <thumbprint>]
   ```

   `--dry-run` prints the entry instead of committing. `--catalog-file catalog.json` edits a
   local copy (try it in BoomerHubb with the environment variable
   `BOOMERHUBB_CATALOG=<path to the file>`).
4. Add the same call to the product's release script, after the release is published, so the
   next release updates the entry by itself. The existing scripts do it in a step named
   "The catalog entry"; a failure there warns and prints the command to run again.

## Format (schema 1)

```jsonc
{
  "schema": 1,                      // BoomerHubb refuses any other number
  "updated": "2026-10-15T08:20:05+00:00",   // set_entry.py
  "products": [ { ... } ]
}
```

Every product:

| Field | Who | Meaning |
|---|---|---|
| `id` | by hand | lower case, unique, never changed (set_entry.py and the app's stage folder use it) |
| `name` | by hand | shown as the card title |
| `description`, `descriptionEn` | by hand | Swedish, and English for an English Windows |
| `type` | by hand | `app`, `navisworks-plugin` or `revit-addin` |
| `version` | set_entry.py | the release tag without `v`, e.g. `1.0.24` |
| `releaseNotes` | set_entry.py | the release page, linked as "Nyheter" |
| `icon` | by hand, optional | square PNG, e.g. `images/regelverket.png` (the app's own `Square150x150Logo`) |
| `screenshot` | by hand, optional | the whole app window in use, about 16:10, e.g. `images/modellvisaren-screenshot.jpg`. Without one the card shows an empty tile with the icon |

Every file is an *asset* object: `pattern` by hand (a wildcard matched against the release's file
names, exactly one must match), `url`, `sha256` and `size` by set_entry.py. BoomerHubb refuses
a download whose SHA-256 differs.

### `app` - an MSIX app

```json
"app": {
  "packageName": "Regelverket",
  "publisher": "CN=Regelverket",
  "certThumbprint": "E113B343...",
  "msix": { "pattern": "Regelverket_*_x64.msix" },
  "zip":  { "pattern": "Regelverket-*-sidladdning.zip" }
}
```

- `packageName`, `publisher` (by hand): the package identity. A downloaded package with another
  identity is refused.
- `certThumbprint` (set_entry.py `--cert-thumbprint`): the signing certificate. If the PC trusts
  it, the signed `.msix` alone is installed, per user, no admin. If not, the sideload `zip` is
  downloaded and its `.cer` imported into `LocalMachine\Root` after a UAC prompt (once per PC and
  certificate, as `Install.cmd` does), then its framework and package. Packages signed with
  another certificate are refused.
- `msix` must be the **signed** package, `zip` the sideload delivery with `Install.cmd`, the
  `.cer` and `Dependencies\x64\`.

Installed apps then update themselves through their own channel; BoomerHubb shows installed
against latest and offers **Uppdatera** when it is behind.

### `navisworks-plugin`

```json
"plugin": {
  "folder": "ViewpointBuilder",
  "assembly": "ViewpointBuilder.dll",
  "zipRoot": "plugin",
  "targets": [
    { "product": "Navisworks Manage", "year": "2025", "asset": { "pattern": "ViewpointBuilder-*.zip" } }
  ]
}
```

- Installed per user, no admin, into `%APPDATA%\Autodesk\<product> <year>\Plugins\<folder>\`.
  `folder` must equal the assembly name: that is what Navisworks loads.
- `zipRoot` is the folder inside the zip whose files are copied there (`""` for the root).
- One target per Navisworks year the plugin is built for. BoomerHubb installs for every year
  that has `C:\Program Files\Autodesk\<product> <year>\Roamer.exe`. Years can share a zip.
- The installed version is the file version of `assembly`, so a copy installed by hand counts.
- While that year's Navisworks runs, nothing is overwritten: the files are staged and copied in
  once it has closed (while BoomerHubb is open, or at its next start).

**An Autodesk bundle** (BoomerHubb 1.0.7 and later): add `"bundle": "<Name>.bundle"`.

```json
"plugin": {
  "bundle": "BIMCamel.bundle",
  "folder": "BIMCamel",
  "assembly": "BIMCamel.dll",
  "zipRoot": "BIMCamel.bundle",
  "targets": [
    { "product": "Navisworks Manage", "year": "2025", "asset": { "pattern": "BIMCamel-ifc-exporter-v*-navisworks.zip" } },
    { "product": "Navisworks Manage", "year": "2026", "asset": { "pattern": "BIMCamel-ifc-exporter-v*-navisworks.zip" } }
  ]
}
```

- `zipRoot` is copied **once** to `%APPDATA%\Autodesk\ApplicationPlugins\<bundle>\`, where each
  Navisworks year finds its own DLL through the bundle's `PackageContents.xml`. All targets share
  one zip.
- The zip must hold `PackageContents.xml` and `<year>\<assembly>` for every target year, or it is
  refused before anything is replaced.
- The installed version is `PackageContents.xml`'s `ApplicationPackage Version`. That is the
  folder the vendor's installer uses too, so a copy installed that way counts.
- It waits while **any** Navisworks runs: every year, Manage or Simulate, reads the bundle.
- Older BoomerHubb versions refuse such an entry harmlessly ("the zip has no <zipRoot>/<assembly>").

## Products we do not release ourselves

A product released by someone else carries `"upstream": "<owner>/<repo>"`, its GitHub repository.
Nobody's release script updates its entry, so `.github/workflows/upstream.yml` checks every such
repository daily. When there is a newer release it fills the entry from it (as `set_entry.py`
does) and opens a **pull request** rather than committing. Merging it is what sends the new version
to every colleague, so look at the release first: it is code from outside the team, and nothing
here scans it.

### `revit-addin` (designed, not installed yet)

BoomerHubb 1.0 lists these as "kommer snart". The intended entry:

```json
"addin": {
  "manifest": "MyAddin.addin",
  "folder": "MyAddin",
  "zipRoot": "addin",
  "targets": [
    { "product": "Revit", "year": "2025", "asset": { "pattern": "MyAddin-*-revit2025.zip" } }
  ]
}
```

installed per user into `%APPDATA%\Autodesk\Revit\Addins\<year>\` (the `.addin` manifest at the
top, the add-in's files in `folder\`), detected by `C:\Program Files\Autodesk\Revit <year>\Revit.exe`
and staged while `Revit.exe` of that year runs, like the Navisworks plugins.

## Pictures

`icon` and `screenshot` are paths relative to `catalog.json` (or full https URLs); the files live in
`images/`. They are public like everything here: a screenshot shows only public test models (the
SBUF models, claude-kit `library/formats/ifc/examples/EXAMPLES.md`), and no user path or project
name. Modellvisaren's shows SBUF `A-40-V-02 - IFC4.ifc`, with the file path in the toolbar
replaced by the file name. About 1600 px wide, JPEG quality 90, keeps the download small.
A new picture reaches every BoomerHubb at its next refresh; no release needed.
