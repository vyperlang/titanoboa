/**
 * This file is loaded by Jupyter Notebook and JupyterLab to expose the
 * BrowserSigner to the frontend.
 */
(() => {
    let isInitialized = false;
    /** Get the Ethereum plugin, initializing it if it hasn't been done yet */
    function getEthereum() {
        const eth = window.ethereum
        const message = 'No Ethereum plugin found. Please authorize the site on your browser wallet.';
        if (!eth) throw new Error(message);
        return eth;
    }

    const rpc = async (method, params) => {
        const eth = getEthereum();
        const result = await eth.request({method, params});
        if (method === "eth_requestAccounts" && !isInitialized) {
            // install callbacks for when the wallet changes
            const isTokenOK = await checkServerToken(config.callbackToken);
            config.debug && console.log(`Boa: Installing callbacks ${config.callbackToken}`, isTokenOK, eth)
            if (!isTokenOK) throw new Error(`Cannot verify the callback token`);
            isInitialized = true;
            const sendClientChanges = changes =>
                callbackAPI(config.callbackToken, stringify(changes))
                    .then(() => config.debug && console.log(`Boa: Client c1hanges sent: ${JSON.stringify(changes)}`))
                    .catch(err => console.error(`Boa: Client changes failed`, changes, err));
            eth.on('accountsChanged', accounts => sendClientChanges({accounts}));
            eth.on('chainChanged', chainId => sendClientChanges({chainId}));
            eth.on('networkChanged', networkId => sendClientChanges({networkId}));
        }
        return result;
    };

    // the following vars get replaced by the backend
    const config = {
        base: `$$JUPYTERHUB_SERVICE_PREFIX`,  // in lab view, base path is deeper
        debug: $$BOA_DEBUG_MODE,
        callbackToken: '$$CALLBACK_TOKEN'
    };

    /** Stringify data, converting big ints to strings */
    const stringify = (data) => JSON.stringify(data, (_, v) => (typeof v === 'bigint' ? v.toString() : v));

    /** Get the value of a cookie with the given name */
    const getCookie = (name) => (document.cookie.match(`\\b${name}=([^;]*)\\b`))?.[1];

    /** Converts a success/failed promise into an object with either a data or error field */
    const parsePromise = promise => promise.then(data => ({data})).catch(error => ({
        error: Object.keys(error).length ? error : {
            message: error.message, // the default error object doesn't have enumerable properties
            stack: error.stack
        }
    }));

    /** Async sleep for the given time */
    const sleep = time => new Promise(resolve => setTimeout(resolve, time));

    const colab = window.colab ?? window.google?.colab; // in the parent window or in an iframe
    /** Calls the callback endpoint with the given token and body */
    async function callbackAPI(token, body) {
        const headers = {['X-XSRFToken']: getCookie('_xsrf')};
        const init = {method: 'POST', body, headers};
        const url = `${config.base}/titanoboa_jupyterlab/callback/${token}`;
        const response = await fetch(url, init);
        return response.text();
    }

    /** Wait until the transaction is mined */
    const waitForTransactionReceipt = async (tx_hash, timeout, poll_latency) => {
        while (true) {
            try {
                const result = await rpc('eth_getTransactionReceipt', [tx_hash]);
                if (result) {
                    return result;
                }
            } catch (err) { // ignore "server error" (happens while transaction is mined)
                if ((err?.info || err)?.error?.code !== -32603) {
                    throw err;
                }
            }
            if (timeout < poll_latency) {
                throw new Error('Timeout waiting for transaction receipt');
            }
            await sleep(poll_latency);
            timeout -= poll_latency;
        }
    };

    /** Call multiple RPC methods in sequence */
    const multiRpc = (payloads) => payloads.reduce(
        async (previousPromise, [method, params]) => [...await previousPromise, await rpc(method, params)],
        [],
    );

    const checkServerToken = async (token) => {
        if (colab) return true;

        // Check backend is online and whether cell was executed before.
        // In Colab this is not needed, eval_js() doesn't replay.
        const response = await fetch(`${config.base}/titanoboa_jupyterlab/callback/${token}`);
        if (response.ok) return true;
        if (response.status === 404 && response.headers.get('Content-Type') === 'application/json') {
            return false; // the cell has already been executed
        }

        const error = 'Could not connect to the titanoboa backend. Please make sure the Jupyter extension is installed by running the following command:';
        const command = 'jupyter lab extension enable boa';
        if (element) {
            element.style.display = "block";  // show the output element in JupyterLab
            element.innerHTML = `<h3 style="color: red">${error}</h3><pre>${command}</pre>`;
        } else {
            prompt(error, command);
        }
        return false;
    }

    /** Call the backend when the given function is called, handling errors */
    const handleCallback = func => async (token, ...args) => {
        if (!await checkServerToken(token)) return;
        const callStr = `${func.name}(${args.map(a => JSON.stringify(a)).join(',')}`;
        const timeout = new Promise(resolve => setTimeout(() => resolve({error: `Timeout waiting for ${callStr}`}), 10000));
        const data = await Promise.race([parsePromise(func(...args)), timeout]);
        const body = stringify(data);
        config.debug && console.log(`Boa: ${callStr}) = ${body};`);
        if (colab) {
            return body;
        }
        await callbackAPI(token, body);
    };

    // if (window._titanoboa && window.ethereum) {
    //     window.ethereum.removeAllListeners(); // cleanup previous browser env
    // }

    // expose functions to window, so they can be called from the BrowserSigner
    window._titanoboa = {
        waitForTransactionReceipt: handleCallback(waitForTransactionReceipt),
        rpc: handleCallback(rpc),
        multiRpc: handleCallback(multiRpc),
    };

    if (element) element.style.display = "none";  // hide the output element in JupyterLab
})();
