// Writes highlights.docx from highlights.txt: Elsevier asks for the highlights as a
// separate editable file with "highlights" in its name, 3-5 bullets of at most 85
// characters each.  Run from the repository root: node submission/scp/build_highlights.js
const fs = require('fs');
const path = require('path');
const { Document, Packer, Paragraph, TextRun } = require('docx');

const here = __dirname;
const lines = fs.readFileSync(path.join(here, 'highlights.txt'), 'utf8')
  .split('\n').map((l) => l.trim()).filter((l) => l.length > 0);
for (const line of lines) {
  if (line.length > 85) throw new Error('highlight longer than 85 characters: ' + line);
}
if (lines.length < 3 || lines.length > 5) throw new Error('need 3-5 highlights, got ' + lines.length);

const doc = new Document({
  sections: [{
    children: [
      new Paragraph({ children: [new TextRun({ text: 'Highlights', bold: true })] }),
      ...lines.map((line) => new Paragraph({ text: line, bullet: { level: 0 } })),
    ],
  }],
});
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(path.join(here, 'highlights.docx'), buffer);
  console.log('wrote submission/scp/highlights.docx with ' + lines.length + ' highlights');
});
