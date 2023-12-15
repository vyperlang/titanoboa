/**
 * This file is loaded by Jupyter Notebook and JupyterLab to expose the
 * BrowserSigner to the frontend.
 */
(() => {
    if (window._titanoboa) return; // don't register twice

    const PLUGIN_API_ROOT = '../titanoboa_jupyterlab';
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
        const headers = {['X-XSRFToken']: getCookie('_xsrf')};
        const init = {method: 'POST', body: stringify(body), headers};
        const url = `${PLUGIN_API_ROOT}/callback/${token}`;
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

    const notebook = window.google?.colab ?? window.colab ?? window.Jupyter?.notebook;
    if (notebook) {
        /** Call the backend when the given function is called, handling errors */
        const registerTarget = (name, func) =>
            notebook.kernel.comms.registerTarget(name, async channel => {
                const onMessage = async message => {
                    console.log(`${name} received`, message)
                    const args = func(message.data);
                    const response = await parsePromise(args);
                    channel.send(JSON.parse(stringify(response)));
                };

                if ('on_msg' in channel) {
                    // older versions of Jupyter Notebook
                    return channel.on_msg(onMessage);
                }
                for await (const message of channel.messages) {
                    await onMessage(message);
                }
            });

        console.log(`Registering callbacks to Jupyter Notebook`);
        window._titanoboa = {
            loadSigner: registerTarget('loadSigner', loadSigner),
            signTransaction: registerTarget('signTransaction', signTransaction),
        };
    } else { // we are in JupyterLab, use API
        /** Call the backend when the given function is called, handling errors */
        const handleCallback = func => async (token, ...args) => {
            const body = await parsePromise(func(...args));
            return callbackAPI(token, body);
        };

        console.log(`Registering callbacks to JupyterLab`);
        // expose functions to window, so they can be called from the BrowserSigner
        window._titanoboa = {
            loadSigner: handleCallback(loadSigner),
            signTransaction: handleCallback(signTransaction)
        };
    }
})();
