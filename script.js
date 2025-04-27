// WebSocket to receive real-time price updates from Bitget
const ws = new WebSocket('wss://ws.bitget.com/spot/v1/market/data');

ws.onopen = () => {
    ws.send(JSON.stringify({
        op: 'subscribe',
        args: ['btcusdt', 'ethusdt'] // Subscribe to your pairs
    }));
};

ws.onmessage = (event) => {
    const marketData = JSON.parse(event.data);
    if (marketData && marketData.data) {
        document.getElementById('price').innerText = `Price: ${marketData.data[0].last}`;
    }
};

// Handle form submission and API call to your serverless function
document.getElementById('grid-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    
    const pair = document.getElementById('pair').value;
    const quantity = document.getElementById('quantity').value;
    const price = document.getElementById('price').value;

    try {
        const response = await fetch('/api/trade', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ pair, quantity, price })
        });
        const data = await response.json();
        console.log('Order placed:', data);
        alert('Order placed successfully');
    } catch (error) {
        console.error('Error placing order:', error);
        alert('Error placing order');
    }
});