# NapisyTWON

A modern PDF annotation tool for adding numbered labels to PDF documents.

## Features

### Core Features
- **PDF Viewing** - Open and view PDF documents with smooth rendering
- **Number Annotations** - Click to place numbered labels on any page
- **Drag & Drop Positioning** - Click and drag to reposition annotations
- **Multi-page Support** - Navigate between pages with thumbnail preview

### UI Features
- **Modern Interface** - Clean PySide6-based UI with Fusion style
- **Thumbnail Sidebar** - Page thumbnails for quick navigation
- **Zoom & Pan** - Mouse wheel zoom, middle-click pan
- **Keyboard Shortcuts** - Full keyboard navigation support

### Style Customization
- **Font Selection** - Choose from all system fonts
- **Size Control** - Adjustable font size (8-200pt)
- **Colors** - Customizable text and background colors
- **Opacity** - Adjustable background transparency
- **Style Presets** - Save and load style configurations

### Workflow Features
- **Undo/Redo** - Full undo/redo support (Ctrl+Z/Y)
- **Auto-increment** - Numbers auto-increment after placement
- **Recent Files** - Quick access to recently opened files
- **Export Options** - Export page as image, export/import positions

## Installation

### Requirements
- Python 3.9+
- PySide6
- PyMuPDF (fitz)
- Pillow

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

Or open a PDF directly:

```bash
python main.py document.pdf
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O | Open PDF |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+Z | Undo |
| Ctrl+Y / Ctrl+Shift+Z | Redo |
| Ctrl+E | Export page as image |
| Delete | Delete selected annotation |
| Escape | Deselect |
| Left/Right | Previous/Next page |
| Ctrl+0 | Fit to window |
| Ctrl+1 | Actual size (100%) |
| Ctrl++ | Zoom in |
| Ctrl+- | Zoom out |
| Mouse wheel | Scroll (or zoom with Ctrl) |
| Middle-click drag | Pan view |

## Usage

1. **Open a PDF** - File > Open or Ctrl+O
2. **Configure style** - Set font, size, colors in toolbar
3. **Place numbers** - Click on the page to place a number
4. **Reposition** - Click and drag existing numbers to move them
5. **Navigate** - Use thumbnails or arrow keys to change pages
6. **Save** - File > Save to apply annotations to PDF

## File Formats

- **PDF** - Native format, annotations saved as FreeText annotations
- **JSON** - Export/import annotation positions for backup or transfer

## Architecture

```
NapisyTWON/
├── main.py              # Application entry point
├── requirements.txt     # Python dependencies
├── src/
│   ├── main_window.py   # Main application window
│   ├── pdf_viewer.py    # PDF canvas with zoom/pan
│   ├── thumbnail_panel.py # Page thumbnails
│   ├── models.py        # Data models (annotations, styles)
│   └── undo_manager.py  # Undo/redo system
└── resources/           # Icons and assets
```

## License

MIT License - feel free to use and modify.

## Credits

Built with:
- [PySide6](https://wiki.qt.io/Qt_for_Python) - Qt for Python
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF rendering
- [Pillow](https://python-pillow.org/) - Image processing
