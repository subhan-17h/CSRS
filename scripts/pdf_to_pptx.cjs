"use strict";

const fs = require("node:fs");
const path = require("node:path");
const PptxGenJS = require("pptxgenjs");

const [manifestPath, outputPath] = process.argv.slice(2);
if (!manifestPath || !outputPath) {
  process.stderr.write("usage: node pdf_to_pptx.cjs PAGES_JSON OUTPUT_PPTX\n");
  process.exit(2);
}

const imagePaths = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
if (!Array.isArray(imagePaths) || imagePaths.length === 0) {
  throw new Error("page manifest must contain at least one image");
}

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Muhammad Subhan Amir";
pptx.company = "Information Technology University";
pptx.subject = "Image-based export of the verified CSRS presentation PDF";
pptx.title = "CSRS Internship Presentation";
pptx.lang = "en-US";

for (const [index, imagePath] of imagePaths.entries()) {
  const slide = pptx.addSlide();
  slide.background = { color: "FFFFFF" };
  slide.addImage({
    path: path.resolve(imagePath),
    altText: `PDF page ${index + 1}`,
    x: 0,
    y: 0,
    w: 13.333333333333334,
    h: 7.5,
  });
}

pptx.writeFile({ fileName: outputPath, compression: true }).catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
