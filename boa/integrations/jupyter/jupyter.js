/**
 * This file is loaded by Jupyter Notebook and JupyterLab to expose the
 * BrowserSigner to the frontend.
 */
(() => {
    let provider; // cache the provider to avoid re-creating it every time
    const getEthersProvider = () => {
        if (provider) return provider;
        const {ethereum} = window;
        if (!ethereum) {
            throw new Error('No Ethereum plugin found. Please authorize the site on your browser wallet.');
        }
        return provider = new ethers.BrowserProvider(ethereum);
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

    const colab = window.colab ?? window.google?.colab; // in the parent window or in an iframe
    /** Calls the callback endpoint with the given token and body */
    async function callbackAPI(token, body) {
        const headers = {['X-XSRFToken']: getCookie('_xsrf')};
        const init = {method: 'POST', body, headers};
        const url = `../titanoboa_jupyterlab/callback/${token}`;
        const response = await fetch(url, init);
        return response.text();
    }

    /** Load the signer via ethers user */
    const loadSigner = async () => {
        const signer = await getEthersProvider().getSigner();
        return signer.getAddress();
    };

    /** Sign a transaction via ethers */
    async function signTransaction(transaction) {
        const signer = await getEthersProvider().getSigner();
        return signer.sendTransaction(transaction);
    }

    /** Call an RPC method via ethers */
    const rpc = (method, params) => getEthersProvider().send(method, params);

    /** Call multiple RPCs in sequence */
    const multiRpc = (payloads) => payloads.reduce(
        async (previousPromise, [method, params]) => [...await previousPromise, await rpc(method, params)],
        [],
    );

    /** Call the backend when the given function is called, handling errors */
    const handleCallback = func => async (token, ...args) => {
        const body = stringify(await parsePromise(func(...args)));
        // console.log(`Boa: ${func.name}(${args.map(a => JSON.stringify(a)).join(',')}) = ${body};`);
        return colab ? body : callbackAPI(token, body);
    };

    // expose functions to window, so they can be called from the BrowserSigner
    window._titanoboa = {
        loadSigner: handleCallback(loadSigner),
        signTransaction: handleCallback(signTransaction),
        rpc: handleCallback(rpc),
        multiRpc: handleCallback(multiRpc),
    };
})();
