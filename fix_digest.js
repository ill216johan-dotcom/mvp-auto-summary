const fs = require('fs');
const data = JSON.parse(fs.readFileSync('C:/Projects/mvp-auto-summary/wf02_full.json','utf8'));
const nodes = data.data.nodes;

const newCode = `const meta = $('Aggregate Transcripts').first().json;
const msg = $json.choices && $json.choices[0] && $json.choices[0].message ? $json.choices[0].message : {};
// GLM-4.7-flash is a thinking model: final answer in content, chain-of-thought in reasoning_content
// Use content if non-empty, else fall back to reasoning_content
const rawContent = (msg.content || '').trim();
const rawReasoning = (msg.reasoning_content || '').trim();
const summaryText = rawContent || rawReasoning || 'Сводка не получена.';
const leadList = Array.isArray(meta.leadIds) && meta.leadIds.length > 0
  ? meta.leadIds.map((id) => \`LEAD-\${id}\`).join(', ')
  : '—';
const header = \`Ежедневный дайджест за \${meta.dateLabel}\\nВстреч: \${meta.count}\\nКлиенты: \${leadList}\`;
const digest = \`\${header}\\n\\n\${summaryText}\`.trim();

return [{
  json: {
    digest,
    summaryText,
    rowIds: meta.rowIds
  }
}];`;

for (const n of nodes) {
  if (n.name === 'Build Digest') {
    n.parameters.jsCode = newCode;
    console.log('Updated Build Digest');
  }
}

const payload = {
  name: data.data.name,
  nodes: data.data.nodes,
  connections: data.data.connections,
  settings: data.data.settings,
  staticData: data.data.staticData
};
fs.writeFileSync('C:/Projects/mvp-auto-summary/wf02_updated.json', JSON.stringify(payload));
console.log('Saved wf02_updated.json');
