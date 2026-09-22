# Publish a Book as standalone HTML

Open a Story's **Book** workspace, arrange chapters and select the telling and passage range for each scene, then save the manuscript. **Publish → Prepare publication files** offers HTML alongside DOCX and EPUB. All three files use the same saved selection. Change the **Include a linked contents list in HTML** checkbox before preparing to include or omit its chapter navigation.

The HTML download is a UTF-8 file with its own reading and print styles. Open it directly in a browser without the Study, an internet connection or JavaScript. It includes the publication title, author and language, semantic chapter headings and the selected prose. **Print scene titles** in Book organization controls scene headings; otherwise a scene break separates scenes within each chapter. Browser printing starts each chapter on a new page.

Paragraphs, line breaks, Unicode and prose spacing are preserved. As with the existing Book formats, prose is literal text: Markdown markers, raw HTML, image references and URLs are not executed or expanded into external resources. Long words wrap at narrow widths. No fonts, scripts, images or other assets are downloaded while reading.

Publication exports contain selected prose and explicit publication metadata. Author notes, bookmarks, prompts, model inputs, branch names and diagnostics, source archives and unselected tellings are excluded. Preparing freezes the selection and HTML contents option; later Book edits do not change an already prepared file. An empty Book, empty chapter or scene left without prose by contribution exclusion must be corrected before preparing.

Private workspace archives preserve Book selections for later preparation after restore. Prepared download snapshots stay installation-local under the existing publication contract; the downloaded HTML itself is portable. No HTML hosting or upload occurs when preparing or downloading a publication.

Measured backend, browser, offline and print verification is recorded in [v090-validation.md](v090-validation.md). Dedicated e-reader behavior and live-model prose quality are separate from HTML acceptance.
