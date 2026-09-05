const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.join(__dirname, "..");
const renderer = fs.readFileSync(path.join(root, "components/ui/SafeMarkdown.tsx"), "utf8");
const assistant = fs.readFileSync(path.join(root, "app/page.tsx"), "utf8");
const knowledgeBase = fs.readFileSync(path.join(root, "components/views/KnowledgeBaseView.tsx"), "utf8");

test("SafeMarkdown uses a real GFM renderer without enabling raw HTML", () => {
  assert.match(renderer, /react-markdown/);
  assert.match(renderer, /remark-gfm/);
  assert.match(renderer, /skipHtml/);
  assert.doesNotMatch(renderer, /dangerouslySetInnerHTML/);
});

test("SafeMarkdown restricts rendered links to safe protocols", () => {
  assert.match(renderer, /url\.protocol === "https:"/);
  assert.match(renderer, /url\.protocol === "http:"/);
  assert.match(renderer, /url\.protocol === "mailto:"/);
  assert.match(renderer, /rel="noreferrer noopener"/);
});

test("SafeMarkdown recognizes fenced code without a language label", () => {
  assert.match(renderer, /rawValue\.includes\("\\n"\)/);
});

test("Assistant and synthesized Knowledge Base answers share SafeMarkdown", () => {
  assert.match(assistant, /<SafeMarkdown content=\{msg\.content\}/);
  assert.match(knowledgeBase, /<SafeMarkdown content=\{displayResult\.answer\}/);
  assert.match(knowledgeBase, /whitespace-pre-wrap[\s\S]*font-mono/);
});
