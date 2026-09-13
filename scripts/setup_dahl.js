const fs = require('fs');
const crypto = require('crypto');
const path = require('path');
const uuidv4 = crypto.randomUUID;

const DB_PATH = 'C:/Users/91700/.omniroute/storage.sqlite';
const ENV_PATH = 'C:/Users/91700/.omniroute/.env';

// 1. Read STORAGE_ENCRYPTION_KEY from .env
let secret = '';
if (fs.existsSync(ENV_PATH)) {
  const envContent = fs.readFileSync(ENV_PATH, 'utf8');
  for (const line of envContent.split('\n')) {
    if (line.startsWith('STORAGE_ENCRYPTION_KEY=')) {
      secret = line.substring('STORAGE_ENCRYPTION_KEY='.length).trim();
    }
  }
}

// 2. Encryption function
function encrypt(plaintext) {
  if (!secret) {
    console.log('No secret found, returning plaintext');
    return plaintext;
  }
  const key = crypto.scryptSync(secret, 'omniroute-field-encryption-v1', 32);
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  let encrypted = cipher.update(plaintext, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag().toString('hex');
  return `enc:v1:${iv.toString('hex')}:${encrypted}:${authTag}`;
}

const dahlApiKey = process.env.DAHL_API_KEY || process.argv[2] || '';
if (!dahlApiKey) {
  console.log('No DAHL_API_KEY supplied via env or argument. Fetching or using existing credentials...');
}
const encryptedKey = dahlApiKey ? encrypt(dahlApiKey) : null;

const Database = require(path.join(process.env.APPDATA, 'npm/node_modules/omniroute/node_modules/better-sqlite3'));
const db = new Database(DB_PATH);

// 3. Upsert Provider Connection for dahl
const existingConn = db.prepare('SELECT id FROM provider_connections WHERE provider = ?').get('dahl');
const connId = existingConn ? existingConn.id : uuidv4();
const now = new Date().toISOString();

const providerSpecificData = JSON.stringify({
  autoSync: true,
  apiKeyHealth: {},
  customUserAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
});

if (existingConn) {
  console.log(`Updating existing dahl provider connection (${connId})...`);
  if (encryptedKey) {
    db.prepare(`
      UPDATE provider_connections SET
        api_key = ?,
        is_active = 1,
        test_status = 'active',
        error_code = NULL,
        last_error = NULL,
        last_error_at = NULL,
        last_error_type = NULL,
        backoff_level = 0,
        rate_limited_until = NULL,
        provider_specific_data = ?,
        updated_at = ?
      WHERE id = ?
    `).run(encryptedKey, providerSpecificData, now, connId);
  } else {
    db.prepare(`
      UPDATE provider_connections SET
        is_active = 1,
        test_status = 'active',
        error_code = NULL,
        last_error = NULL,
        last_error_at = NULL,
        last_error_type = NULL,
        backoff_level = 0,
        rate_limited_until = NULL,
        provider_specific_data = ?,
        updated_at = ?
      WHERE id = ?
    `).run(providerSpecificData, now, connId);
  }
} else {
  if (!encryptedKey) {
    throw new Error('DAHL_API_KEY required to create a new dahl connection.');
  }
  console.log(`Inserting new dahl provider connection (${connId})...`);
  db.prepare(`
    INSERT INTO provider_connections (
      id, provider, auth_type, name, display_name, priority, is_active,
      test_status, api_key, provider_specific_data, proxy_enabled, per_key_proxy_enabled,
      quota_visible, consecutive_use_count, rate_limit_protection, backoff_level,
      created_at, updated_at
    ) VALUES (
      ?, 'dahl', 'apikey', 'dahl-main', 'Dahl Main', 10, 1,
      'active', ?, ?, 1, 0,
      1, 0, 0, 0,
      ?, ?
    )
  `).run(connId, encryptedKey, providerSpecificData, now, now);
}

// 4. Upsert Combo for dahl
const comboData = {
  id: "combo-dahl",
  name: "dahl",
  models: [
    {
      id: "dahl-model-1-minimax",
      kind: "model",
      model: "dahl/MiniMaxAI/MiniMax-M2.7",
      providerId: "dahl",
      weight: 0
    },
    {
      id: "dahl-model-2-deepseek",
      kind: "model",
      model: "dahl/deepseek-ai/DeepSeek-V4-Flash-0731",
      providerId: "dahl",
      weight: 0
    }
  ],
  strategy: "round-robin",
  config: {
    maxRetries: 2,
    retryDelayMs: 1000,
    trackMetrics: true
  },
  isHidden: false,
  sortOrder: 6,
  createdAt: now,
  updatedAt: now,
  version: 2,
  isActive: true,
  capabilities: {
    multimodal: true,
    reasoning: true,
    caching: false
  }
};

const existingCombo = db.prepare('SELECT id FROM combos WHERE name = ? OR id = ?').get('dahl', 'combo-dahl');
if (existingCombo) {
  console.log(`Updating combo dahl (${existingCombo.id})...`);
  db.prepare(`
    UPDATE combos SET
      name = 'dahl',
      data = ?,
      updated_at = ?
    WHERE id = ?
  `).run(JSON.stringify(comboData), now, existingCombo.id);
} else {
  console.log(`Inserting combo dahl (combo-dahl)...`);
  db.prepare(`
    INSERT INTO combos (
      id, name, data, sort_order, created_at, updated_at, system_message, tool_filter_regex, context_cache_protection
    ) VALUES (
      'combo-dahl', 'dahl', ?, 6, ?, ?, NULL, NULL, 0
    )
  `).run(JSON.stringify(comboData), now, now);
}

// Also add dahl models to free only combo
const freeOnlyRow = db.prepare('SELECT id, data FROM combos WHERE name = ?').get('free only');
if (freeOnlyRow) {
  try {
    const freeData = JSON.parse(freeOnlyRow.data);
    freeData.models = freeData.models.filter(m => m.providerId !== 'dahl' && (!m.model || !m.model.includes('dahl')));
    freeData.models.push(
      {
        id: "free-only-model-dahl-minimax",
        kind: "model",
        model: "dahl/MiniMaxAI/MiniMax-M2.7",
        providerId: "dahl",
        weight: 0
      },
      {
        id: "free-only-model-dahl-deepseek",
        kind: "model",
        model: "dahl/deepseek-ai/DeepSeek-V4-Flash-0731",
        providerId: "dahl",
        weight: 0
      }
    );
    freeData.updatedAt = now;
    db.prepare('UPDATE combos SET data = ?, updated_at = ? WHERE id = ?').run(
      JSON.stringify(freeData), now, freeOnlyRow.id
    );
  } catch (e) {
    console.error('Error updating free only combo:', e);
  }
}

db.close();
console.log('Setup dahl completed successfully in OmniRoute storage.sqlite!');
