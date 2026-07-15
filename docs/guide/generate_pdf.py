#!/usr/bin/env python3
"""
Generate a PDF from the markdown guide files.
Requires: pip install markdown2 pdfkit wkhtmltopdf OR pip install weasyprint
"""

import os
import subprocess
from pathlib import Path

def generate_html_from_markdown():
    """Generate a single HTML file combining all markdown chapters."""
    guide_dir = Path(__file__).parent
    
    # Order of files to combine
    files = [
        'README.md',
        'TOC.md',
        '01-system-overview.md',
        '02-fastapi-and-layered-architecture.md',
        '03-data-model-and-persistence.md',
        '04-authentication-and-security.md',
        '05-rooms-matchmaking-and-game-engine.md',
        '06-websocket-protocol-and-realtime-flow.md',
        '07-redis-strategy.md',
        '08-testing-and-dev-workflow.md',
        '09-extension-playbook.md',
        '10-90-minute-onboarding-path.md',
        '11-contributor-task-map.md',
        '12-troubleshooting-playbook.md',
        '13-architecture-decision-log.md',
        '14-realtime-protocol-quick-reference.md',
    ]
    
    # Combine all markdown files
    combined_content = ""
    for filename in files:
        filepath = guide_dir / filename
        if filepath.exists():
            with open(filepath, 'r') as f:
                content = f.read()
                combined_content += content + "\n\n---\n\n"
    
    # Generate HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Developer Guide: Cards Against Humanity Clone Backend</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        
        h1 {{
            color: #0066cc;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
            page-break-after: avoid;
        }}
        
        h2 {{
            color: #0052a3;
            margin-top: 30px;
            page-break-after: avoid;
        }}
        
        h3 {{
            color: #003d7a;
            page-break-after: avoid;
        }}
        
        h4, h5, h6 {{
            page-break-after: avoid;
        }}
        
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.95em;
        }}
        
        pre {{
            background-color: #f4f4f4;
            border-left: 4px solid #0066cc;
            padding: 12px;
            overflow-x: auto;
            border-radius: 3px;
            page-break-inside: avoid;
        }}
        
        pre code {{
            background-color: transparent;
            padding: 0;
        }}
        
        blockquote {{
            border-left: 4px solid #ddd;
            padding-left: 16px;
            margin-left: 0;
            color: #666;
            font-style: italic;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
            page-break-inside: avoid;
        }}
        
        table, th, td {{
            border: 1px solid #ddd;
        }}
        
        th {{
            background-color: #f4f4f4;
            padding: 12px;
            text-align: left;
        }}
        
        td {{
            padding: 12px;
        }}
        
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        ul, ol {{
            margin: 12px 0;
        }}
        
        li {{
            margin: 6px 0;
        }}
        
        hr {{
            border: none;
            border-top: 2px solid #ddd;
            margin: 40px 0;
            page-break-after: avoid;
        }}
        
        .toc {{
            background-color: #f0f7ff;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        
        .note {{
            background-color: #fffbea;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin: 12px 0;
            border-radius: 3px;
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 10px;
                font-size: 14px;
            }}
        }}
        
        @media print {{
            body {{
                background-color: white;
            }}
            
            a {{
                color: #0066cc;
            }}
            
            h1, h2, h3, h4, h5, h6 {{
                page-break-after: avoid;
                page-break-inside: avoid;
            }}
            
            ul, ol, dl {{
                page-break-inside: avoid;
            }}
            
            pre, code, table {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div id="content">
        {convert_markdown_to_html(combined_content)}
    </div>
    <script>
        document.title = 'Developer Guide: Cards Against Humanity Clone Backend';
    </script>
</body>
</html>"""
    
    return html_content

def convert_markdown_to_html(markdown_text):
    """Convert markdown to HTML using simple string replacement (no external deps)."""
    import re
    
    html = markdown_text
    
    # Convert code blocks
    html = re.sub(
        r'```([a-z]+)?\n(.*?)\n```',
        r'<pre><code class="language-\1">\2</code></pre>',
        html,
        flags=re.DOTALL
    )
    
    # Convert inline code
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
    
    # Convert headers
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^##### (.+)$', r'<h5>\1</h5>', html, flags=re.MULTILINE)
    
    # Convert bold
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.+?)__', r'<strong>\1</strong>', html)
    
    # Convert italic
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'_(.+?)_', r'<em>\1</em>', html)
    
    # Convert links
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    
    # Convert horizontal rules
    html = re.sub(r'^---+$', r'<hr>', html, flags=re.MULTILINE)
    
    # Convert lists (basic)
    html = re.sub(r'^\* (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'^\- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    
    # Wrap lists
    html = re.sub(r'(?:<li>.*?</li>\n)+', lambda m: '<ul>\n' + m.group(0) + '</ul>\n', html, flags=re.DOTALL)
    
    # Convert blockquotes
    html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
    
    # Convert paragraphs
    lines = html.split('\n')
    result = []
    for line in lines:
        if line and not any(line.startswith(tag) for tag in ['<h', '<p', '<ul', '<ol', '<pre', '<blockquote', '<hr']):
            line = f'<p>{line}</p>'
        result.append(line)
    html = '\n'.join(result)
    
    return html

def main():
    """Generate HTML and attempt PDF conversion."""
    guide_dir = Path(__file__).parent
    
    print("📄 Generating HTML from markdown...")
    html_content = generate_html_from_markdown()
    
    html_file = guide_dir / 'Developer-Guide-CAH-Backend.html'
    with open(html_file, 'w') as f:
        f.write(html_content)
    print(f"✅ HTML generated: {html_file}")
    
    # Try PDF conversion with available tools
    pdf_file = guide_dir.parent / 'Developer-Guide-CAH-Backend.pdf'
    
    try:
        # Try weasyprint first
        try:
            import weasyprint
            print("📝 Converting to PDF with weasyprint...")
            weasyprint.HTML(str(html_file)).write_pdf(str(pdf_file))
            print(f"✅ PDF generated: {pdf_file}")
            return
        except ImportError:
            pass
        
        # Try wkhtmltopdf
        try:
            subprocess.run(['wkhtmltopdf', str(html_file), str(pdf_file)], 
                         check=True, capture_output=True)
            print(f"✅ PDF generated: {pdf_file}")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # Try pandoc
        try:
            subprocess.run(['pandoc', str(html_file), '-o', str(pdf_file)], 
                         check=True, capture_output=True)
            print(f"✅ PDF generated: {pdf_file}")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        print("⚠️  PDF generation tools not available.")
        print(f"📝 HTML file generated at: {html_file}")
        print("\n📖 To convert to PDF, you can:")
        print("   1. Open the HTML in a browser and print to PDF")
        print("   2. Install: pip install weasyprint")
        print("   3. Install: brew install wkhtmltopdf (macOS) or apt install wkhtmltopdf (Linux)")
        print("   4. Install: apt install pandoc (Linux)")
        
    except Exception as e:
        print(f"❌ Error during PDF generation: {e}")
        print(f"✅ HTML file generated at: {html_file}")
        print("   You can open this in a browser and print to PDF manually.")

if __name__ == '__main__':
    main()
