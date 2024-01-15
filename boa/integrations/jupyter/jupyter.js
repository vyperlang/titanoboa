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
    const stringify = (data) => JSON.stringify(data, (_, v) => (typeof v === 'bigint' ? v.toString() : v));
    const getCookie = (name) => (document.cookie.match(`\\b${name}=([^;]*)\\b`))?.[1];
    const parsePromise = promise =>
        promise.then(data => ({data})).catch(e => {
            console.error(e.stack || e.message);
            return {error: e.message};
        });

    const colab = window.colab ?? window.google?.colab; // in the parent window or in an iframe
    const detectEnv = () => colab ? {
        apiRoot: `https://localhost:8888`, // this gets proxied to the backend by Colab
        headers: {"x-colab-tunnel": "Google"}
    } : {
        apiRoot: '../titanoboa_jupyterlab',
        headers: {['X-XSRFToken']: getCookie('_xsrf')}
    };

    /** Calls the callback endpoint with the given token and body */
    async function callbackAPI(token, body) {
        const {apiRoot, headers} = detectEnv();
        const init = {method: 'POST', body: stringify(body), headers};
        const url = `${apiRoot}/callback/${token}`;
        const response = await fetch(url, {...init, headers});
        return response.text();
    }

    /** Load the signer via ethers user */
    const loadSigner = async () => {
        const provider = getEthersProvider();
        console.log(`Loading the user's signer`);
        const signer = await provider.getSigner();
        return signer.getAddress();
    };

    /** Sign a transaction via ethers */
    async function signTransaction(transaction) {
        const provider = getEthersProvider();
        console.log('Starting to sign transaction');
        const signer = await provider.getSigner();
        return signer.sendTransaction(transaction);
    }

    /** Call the backend when the given function is called, handling errors */
    const handleCallback = func => async (token, ...args) => {
        const body = await parsePromise(func(...args));
        if (colab) {
            // Colab expects the response to be JSON
            return JSON.stringify(body);
        }
        const responseText = await callbackAPI(token, body);
        console.log(`Callback ${token} => ${responseText}`);
    };

    console.log(`Registering Boa callbacks`);
    // expose functions to window, so they can be called from the BrowserSigner
    window._titanoboa = {
        loadSigner: handleCallback(loadSigner),
        signTransaction: handleCallback(signTransaction)
    };
})();
