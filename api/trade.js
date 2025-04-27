const axios  = require('axios');
const crypto = require('crypto');

const API_KEY       = process.env.BITGET_API_KEY;
const API_SECRET    = process.env.BITGET_API_SECRET;
const API_PASSPHRASE= process.env.BITGET_API_PASSPHRASE;
const BASE_URL      = 'https://api.bitget.com/api/v1';

// Sign parameters
function sign(params) {
  const qs = new URLSearchParams(params).toString();
  return crypto.createHmac('sha256', API_SECRET).update(qs).digest('hex');
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).end();
  const { symbol, quantity, price } = req.body;
  const params = {
    symbol, size: quantity, price,
    apiKey: API_KEY, passphrase: API_PASSPHRASE,
    timestamp: Date.now()
  };
  params.sign = sign(params);
  try {
    const r = await axios.post(`${BASE_URL}/spot/v1/order`, params);
    res.status(200).json(r.data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
};