/**
 * Minimal, dependency-free Markdown renderer for the patient report.
 *
 * Supports the exact subset the backend `render_markdown` emits: h1-h3
 * headings, blockquotes, GitHub-style tables, nested bullet lists, bold and
 * inline code. Everything is rendered as React elements (never
 * dangerouslySetInnerHTML), so report text can never inject markup.
 */
const INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`)/g;

function inlineNodes(text, keyPrefix) {
  const nodes = [];
  let last = 0;
  let match;
  let n = 0;
  INLINE_RE.lastIndex = 0;
  while ((match = INLINE_RE.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-b${n}`}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(
        <code key={`${keyPrefix}-c${n}`} className="rounded bg-slate-100 px-1 py-0.5 text-[12px] text-navy-800">
          {token.slice(1, -1)}
        </code>
      );
    }
    last = match.index + token.length;
    n += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function splitRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableStart(lines, i) {
  return lines[i]?.trim().startsWith("|") && /^\|[\s:|-]+\|$/.test((lines[i + 1] || "").trim());
}

function renderList(items, keyPrefix) {
  // items: [{ text, children: [...] }]
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item, idx) => (
        <li key={`${keyPrefix}-${idx}`}>
          {inlineNodes(item.text, `${keyPrefix}-${idx}`)}
          {item.children.length > 0 && <div className="mt-1">{renderList(item.children, `${keyPrefix}-${idx}`)}</div>}
        </li>
      ))}
    </ul>
  );
}

function buildList(lines, start, keyPrefix) {
  const roots = [];
  const stack = [{ depth: -1, items: roots }];
  let i = start;
  while (i < lines.length && /^\s*-\s+/.test(lines[i])) {
    const indent = lines[i].match(/^\s*/)[0].length;
    const text = lines[i].trim().replace(/^-\s+/, "");
    const item = { text, children: [] };
    while (stack.length > 1 && indent <= stack[stack.length - 1].depth) stack.pop();
    stack[stack.length - 1].items.push(item);
    stack.push({ depth: indent, items: item.children });
    i += 1;
  }
  return [renderList(roots, keyPrefix), i];
}

export default function MarkdownView({ content, className = "" }) {
  if (!content) return null;
  const lines = content.split(/\r?\n/);
  const blocks = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    if (isTableStart(lines, i)) {
      const header = splitRow(lines[i]);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push(
        <div key={`t${key++}`} className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-b border-slate-300 text-xs uppercase text-slate-500">
                {header.map((cell, c) => (
                  <th key={c} className="py-1.5 pr-4 font-semibold">
                    {inlineNodes(cell, `th${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={r} className="border-b border-slate-100">
                  {row.map((cell, c) => (
                    <td key={c} className="py-1.5 pr-4 tabular-nums">
                      {inlineNodes(cell, `td${r}-${c}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (trimmed.startsWith("### ")) {
      blocks.push(
        <h3 key={`h3${key++}`} className="pt-1 text-sm font-bold text-navy-900">
          {inlineNodes(trimmed.slice(4), "h3")}
        </h3>
      );
      i += 1;
      continue;
    }
    if (trimmed.startsWith("## ")) {
      blocks.push(
        <h2 key={`h2${key++}`} className="mt-4 border-t border-slate-100 pt-4 text-base font-bold text-navy-900">
          {inlineNodes(trimmed.slice(3), "h2")}
        </h2>
      );
      i += 1;
      continue;
    }
    if (trimmed.startsWith("# ")) {
      blocks.push(
        <h1 key={`h1${key++}`} className="text-lg font-bold text-navy-900">
          {inlineNodes(trimmed.slice(2), "h1")}
        </h1>
      );
      i += 1;
      continue;
    }

    if (trimmed.startsWith("> ")) {
      const quote = [];
      while (i < lines.length && lines[i].trim().startsWith("> ")) {
        quote.push(lines[i].trim().slice(2));
        i += 1;
      }
      blocks.push(
        <blockquote key={`q${key++}`} className="rounded-lg border-l-4 border-amber-300 bg-amber-50 px-3 py-2 text-amber-900">
          {quote.map((q, qIdx) => (
            <p key={qIdx}>{inlineNodes(q, `q${qIdx}`)}</p>
          ))}
        </blockquote>
      );
      continue;
    }

    if (/^\s*-\s+/.test(line)) {
      const [list, next] = buildList(lines, i, `l${key}`);
      blocks.push(<div key={`lw${key++}`}>{list}</div>);
      i = next;
      continue;
    }

    const para = [trimmed];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith("#") &&
      !lines[i].trim().startsWith("> ") &&
      !/^\s*-\s+/.test(lines[i]) &&
      !isTableStart(lines, i)
    ) {
      para.push(lines[i].trim());
      i += 1;
    }
    blocks.push(<p key={`p${key++}`}>{inlineNodes(para.join(" "), `p${key}`)}</p>);
  }

  return <div className={`space-y-2.5 text-sm leading-relaxed text-slate-700 ${className}`}>{blocks}</div>;
}
