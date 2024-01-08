/**
 * This file is loaded by Jupyter Notebook and JupyterLab to expose the
 * BrowserSigner to the frontend.
 */
(() => {
    if (window._titanoboa) return; // don't register twice

    const getEthersProvider = () => {
        const {ethereum} = window;
        if (!ethereum) throw new Error('No Ethereum browser plugin found');
        return new ethers.BrowserProvider(ethereum);
    };
    const stringify = (data) => JSON.stringify(data, (_, v) => (typeof v === 'bigint' ? v.toString() : v));
    const getCookie = (name) => (document.cookie.match(`\\b${name}=([^;]*)\\b`))?.[1];
    const parsePromise = promise =>
        promise.then(data => ({data})).catch(e => {
            console.error(e.stack || e.message);
            return {error: e.message};
        });

    /** Calls the callback endpoint with the given token and body */
    async function callbackAPI(token, body) {
        const apiRoot = window.colab ? `/tun/m/${window.colab.global.notebook.kernel.endpoint.managedId}/_proxy/8888?authuser=0` : '../titanoboa_jupyterlab';
        const headers = window.colab ? {"x-colab-tunnel": "Google"} : {['X-XSRFToken']: getCookie('_xsrf')};
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
        return callbackAPI(token, body);
    };

    console.log(`Registering Boa callbacks`);
    // expose functions to window, so they can be called from the BrowserSigner
    window._titanoboa = {
        loadSigner: handleCallback(loadSigner),
        signTransaction: handleCallback(signTransaction)
    };
})();
