/**
 * This file is loaded by Jupyter Notebook and JupyterLab to expose the
 * BrowserSigner to the frontend.
 */
(() => {
    const getEthersProvider = () => {
        const {ethereum} = window;
        if (!ethereum) {
            throw new Error('No Ethereum browser plugin found');
        }
        return new ethers.BrowserProvider(ethereum);
    };

    /** Stringify data, converting big ints to strings */
    const stringify = (data) => JSON.stringify(data, (_, v) => (typeof v === 'bigint' ? v.toString() : v));

    /** Get the value of a cookie with the given name */
    const getCookie = (name) => (document.cookie.match(`\\b${name}=([^;]*)\\b`))?.[1];

    /** Converts a success/failed promise into an object with either a data or error field */
    const parsePromise = promise =>
        promise.then(data => ({data})).catch(e => {
            console.log(e.message, e.stack);
            return {error: e.message};
        });

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
    const loadSigner = async (provider) => {
        const signer = await provider.getSigner();
        return signer.getAddress();
    };

    /** Sign a transaction via ethers */
    async function signTransaction(provider, transaction) {
        const signer = await provider.getSigner();
        return signer.sendTransaction(transaction);
    }

    /** Call an RPC method via ethers */
    const rpc = (provider, method, params) => getEthersProvider().send(method, params);

    /** Call multiple RPCs in sequence, eth_call(payloads) does not work well */
    const multiRpc = (provider, payloads) =>
        payloads.reduce(async (previousPromise, [method, params]) =>
            [...await previousPromise, await rpc(provider, method, params)],
            Promise.resolve([]),
        );

    /** Call the backend when the given function is called, handling errors */
    const handleCallback = func => async (token, ...args) => {
        const body = stringify(await parsePromise(func(getEthersProvider(), ...args)));
        console.log(`Boa: ${func.name}(${args.map(a => JSON.stringify(a)).join(',')}) = ${body};`); // todo: comment out
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
