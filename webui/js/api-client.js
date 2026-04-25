function callApi(methodName, ...args) {
    if (typeof pywebview === 'undefined' || !pywebview.api || typeof pywebview.api[methodName] !== 'function') {
        return Promise.reject(new Error(`API不可用: ${methodName}`));
    }
    return pywebview.api[methodName](...args);
}

function completeModalByResult(modal, result, successMessage, failurePrefix) {
    if (result && result.success) {
        modal.complete(true, successMessage);
        return;
    }
    const message = result && result.message ? result.message : '未知错误';
    modal.complete(false, `${failurePrefix}: ${message}`);
}

window.callApi = callApi;
window.completeModalByResult = completeModalByResult;
