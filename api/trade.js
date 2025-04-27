const axios = require('axios');
const crypto = require('crypto');

// Bitget API credentials
const API_KEY = 'your_bitget_api_key';
const API_SECRET = 'your_bitget_api_secret';
const API_PASSPHRASE = 'your_bitget_api_passphrase';

// API base URL
const BASE_URL = 'https://api.bitget.com/api/v1';

// Helper function to generate the signature for the API request
const generateSignature = (params) => {
    const queryString = new URLSearchParams(params).toString();
    return crypto.createHmac('sha256', API_SECRET).update(queryString).digest('hex');
};

// Function to place a grid order on Bitget
const placeGridOrder = async (symbol, quantity, price) => {
    const params = {
        symbol,
        size: quantity,
        price,
        apiKey: API_KEY,
        passphrase: API_PASSPHRASE,
        timestamp: Date.now(),
    };
    
    const signature = generateSignature(params);
    params.sign = signature;

    try {
        const response = await axios.post(`${BASE_URL}/spot/v1/order`, params);
        return response.data;
    } catch (error) {
        return { error: error.message };
    }
};

// Serverless function endpoint
module.exports = async (req, res) => {
    if (req.method === 'POST') {
        const { pair, quantity, price } = req.body;

        // Call the Bitget API to place the order
        const orderResponse = await placeGridOrder(pair, quantity, price);

        // Return the order response to the client
        res.status(200).json(orderResponse);
    } else {
        res.status(405).send('Method Not Allowed');
    }
};
