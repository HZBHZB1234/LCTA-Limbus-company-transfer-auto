let packageItemManagerCompat = new ItemListManager('install-package-list', {
    emptyMessage: '未找到可用的汉化包',
    itemIcon: 'fa-box',
    onSelect: (item) => {
        addLogMessage(`已选中汉化包: ${item}`, 'info');
    }
});

let installedPackageItemManagerCompat = new ItemListManager('installed-package-list', {
    emptyMessage: '未找到已安装汉化包',
    itemIcon: 'fa-box',
    onSelect: (item) => {
        addLogMessage(`已选中汉化包: ${item}`, 'info');
    }
});

let modItemManagerCompat;
let symlinkStatusCompat;
let symlinkManagerCompat;

async function browseInstallPackageDirectory() {
    const result = await callApi('browse_folder', 'install-package-directory');
    const packageDirInput = document.getElementById('install-package-directory');
    if (packageDirInput && result) {
        packageDirInput.value = result;
        await configManager.updateConfigValue('install-package-directory', result);
        await configManager.flushPendingUpdates();
        refreshInstallPackageList();
    }
}

async function clearPackageDirectory() {
    const packageDirInput = document.getElementById('install-package-directory');
    if (packageDirInput) {
        packageDirInput.value = '';
        await configManager.updateConfigValue('install-package-directory', '');
        await configManager.flushPendingUpdates();
        refreshInstallPackageList();
    }
}

function browseInstallModDirectory() {
    callApi('browse_folder', 'installed-mod-directory').then(async function(result) {
        const modDirInput = document.getElementById('installed-mod-directory');
        if (modDirInput && result) {
            modDirInput.value = result;
            await configManager.updateConfigValue('installed-mod-directory', result);
            await configManager.flushPendingUpdates();
            refreshInstalledModList();
        }
    }).catch(function(error) {
        showMessage('错误', '浏览文件夹时发生错误: ' + error);
    });
}

async function clearModDirectory() {
    const modDirInput = document.getElementById('installed-mod-directory');
    if (modDirInput) {
        modDirInput.value = '';
        await configManager.updateConfigValue('installed-mod-directory', '');
        await configManager.flushPendingUpdates();
        refreshInstalledModList();
    }
}

function refreshInstallPackageList() {
    const packageList = document.getElementById('install-package-list');
    if (!packageList) return;

    packageItemManagerCompat.waitList();
    callApi('get_translation_packages')
        .then(function(result) {
            if (result.success && result.packages && result.packages.length > 0) {
                packageItemManagerCompat.setItems(result.packages);
            } else {
                packageItemManagerCompat.setItems([]);
            }
        })
        .catch(function(error) {
            console.error('获取汉化包列表失败:', error);
            packageItemManagerCompat.showErrorList(error);
        });
}

function installSelectedPackage() {
    const packageName = packageItemManagerCompat.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    const modal = new ProgressModal('安装汉化包');
    modal.addLog(`开始安装汉化包: ${packageName}`);

    callApi('install_translation', packageName, modal.id)
        .then(function(result) {
            completeModalByResult(modal, result, '汉化包安装成功', '安装失败');
        })
        .catch(function(error) {
            modal.complete(false, '安装过程中发生错误: ' + error);
        });
}

function deleteSelectedPackage() {
    const packageName = packageItemManagerCompat.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    showConfirm('确认删除', `确定要删除汉化包 "${packageName}" 吗？此操作不可撤销。`,
        function() {
            callApi('delete_translation_package', packageName)
                .then(function(result) {
                    if (result.success) {
                        packageItemManagerCompat.removeItem(packageName);
                        showMessage('删除成功', `汉化包 "${packageName}" 已被删除`);
                    } else {
                        showMessage('删除失败', `删除汉化包失败: ${result.message}`);
                    }
                })
                .catch(function(error) {
                    showMessage('删除失败', `删除过程中发生错误: ${error}`);
                });
        },
        function() {}
    );
}

function refreshInstalledPackageList() {
    const packageList = document.getElementById('installed-package-list');
    if (!packageList) return;

    installedPackageItemManagerCompat.waitList();
    callApi('get_installed_packages')
        .then(function(result) {
            const box = document.getElementById('enable-lang');
            if (result.success && result.enable && result.packages && result.packages.length > 0) {
                box.checked = true;
                installedPackageItemManagerCompat.setItems(result.packages);
                if (result.selected) {
                    installedPackageItemManagerCompat.setSelectedItem(result.selected);
                }
            } else {
                installedPackageItemManagerCompat.setItems([]);
                if (result.success) {
                    box.checked = false;
                }
            }
            toggleCustomLangGui();
        })
        .catch(function(error) {
            console.error('获取汉化包列表失败:', error);
            installedPackageItemManagerCompat.showErrorList(error);
        });
}

function useSelectedPackage() {
    const packageName = installedPackageItemManagerCompat.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    const modal = new ProgressModal('使用选中汉化包');
    modal.addLog(`开始切换汉化包: ${packageName}`);

    callApi('use_translation', packageName, modal.id)
        .then(function(result) {
            completeModalByResult(modal, result, '汉化包切换成功', '切换失败');
            if (result.success) {
                setTimeout(() => { modal.close(); }, 300);
            }
        })
        .catch(function(error) {
            modal.complete(false, '切换过程中发生错误: ' + error);
        });
}

function deleteInstalledPackage() {
    const packageName = installedPackageItemManagerCompat.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    showConfirm('确认删除', `确定要删除汉化包 "${packageName}" 吗？此操作不可撤销。`,
        function() {
            callApi('delete_installed_package', packageName)
                .then(function(result) {
                    if (result.success) {
                        installedPackageItemManagerCompat.removeItem(packageName);
                        showMessage('删除成功', `汉化包 "${packageName}" 已被删除`);
                    } else {
                        showMessage('删除失败', `删除汉化包失败: ${result.message}`);
                    }
                })
                .catch(function(error) {
                    showMessage('删除失败', `删除过程中发生错误: ${error}`);
                });
        },
        function() {}
    );
}

async function refreshInstalledModList() {
    if (!modItemManagerCompat) {
        modItemManagerCompat = new ToggleItemListManager('install-mod-list', {
            emptyMessage: '未找到模组',
            itemIcon: 'fa-language',
            defaultEnabled: false,
            onSelect: (item) => {
                console.log('选中翻译器:', item);
            },
            onToggle: (item, enabled) => {
                toggleMod(item, enabled);
            }
        });
    }

    modItemManagerCompat.waitList();
    const result = await callApi('find_installed_mod');
    if (result.success) {
        const merged = result.able.concat(result.disable);
        modItemManagerCompat.setItems(merged);
        result.able.forEach(item => {
            modItemManagerCompat.enabledMap[item] = true;
        });
        modItemManagerCompat.updateList();
    }
}

async function toggleMod(item, enable) {
    await callApi('toggle_mod', item, enable);
}

function openModPath() {
    callApi('open_mod_path');
}

async function deleteSelectedMod() {
    const packageName = modItemManagerCompat ? modItemManagerCompat.getSelectedItem() : null;
    if (!packageName) {
        showMessage('提示', '请先选择一个模组');
        return;
    }

    showConfirm('确认删除', `确定要删除模组 "${packageName}" 吗？此操作不可撤销。`,
        async function() {
            const enabledMap = modItemManagerCompat.getEnabledMap();
            const result = await callApi('delete_mod', packageName, enabledMap[packageName]);
            if (result.success) {
                modItemManagerCompat.removeItem(packageName);
            } else {
                showMessage('删除失败', `删除模组失败: ${result.message}`);
            }
        },
        function() {}
    );
}

async function loadSymlinkStatus() {
    try {
        const result = await callApi('get_symlink_status');
        symlinkStatusCompat = result.success ? result.status : {};
    } catch (error) {
        console.log(error);
        addLogMessage(error);
    }
}

async function refreshSymlink() {
    await loadSymlinkStatus();

    symlinkManagerCompat = new ActionButtonItemListManager('symlink-list', {
        actionButtonText: (item) => {
            const symlink = symlinkStatusCompat[item];
            switch (symlink.status) {
                case 'not_exist':
                    return '不存在';
                case 'not_symlink':
                    return '文件夹';
                case 'symlink':
                    return '软链接';
                default:
                    return '处理错误';
            }
        },
        actionButtonCallback: (item) => {
            const symlink = symlinkStatusCompat[item];
            switch (symlink.status) {
                case 'not_symlink':
                    openPath(symlink.path);
                    break;
                case 'symlink':
                    openPath(symlink.target);
                    break;
                default:
                    showMessage('无法处理');
            }
        },
        onSelect: (item) => {
            console.log('选中:', item);
        },
        emptyMessage: '暂无数据',
        itemIcon: 'fa-file'
    });

    symlinkManagerCompat.setItems(['ProjectMoon', 'Unity']);
}

function openPath(path) {
    callApi('run_func', 'open_explorer', path);
}

async function createSymlink() {
    const folderName = symlinkManagerCompat.getSelectedItem();
    const folder = symlinkStatusCompat[folderName];
    try {
        if (folder.status === 'symlink') {
            showConfirm('是否要更换软链接目标？',
                `您已经创建了一个可用的软链接，它的目录是 ${folder.target}，是否更换目录？\n如果您确认继续，请选择您想要更换的目标路径`,
                async function() {
                    const targetDir = await callApi('browse_folder', 'symlink-target-dir');
                    if (!targetDir || targetDir.length === 0) return;
                    const hasContent = await callApi('run_func', 'evaluate_path', targetDir);
                    async function doCreate() {
                        await callApi('run_func', 'remove_symlink', folder.path);
                        await callApi('run_func', 'create_symlink', targetDir, folder.path);
                        await callApi('move_folders', folder.target, targetDir);
                        refreshSymlink();
                    }
                    if (hasContent) {
                        showConfirm('警告', `目标文件夹中含有文件。可能出现非预期行为。\n这有可能导致以下错误: 游戏无法正常启动，点击删除软链接时同时移动目标文件夹下的所有文件。\n正常的做法是创建一个空文件夹用来盛放文件。\n如果你确定知道自己在做什么，请点击确定`, doCreate, () => {});
                    } else {
                        doCreate();
                    }
                },
                () => {}
            );
        } else if (folder.status === 'not_symlink') {
            showConfirm('是否要创建软链接？',
                `如果您确认继续，请选择您想要把数据放在的文件夹`,
                async function() {
                    const targetDir = await callApi('browse_folder', 'symlink-target-dir');
                    if (!targetDir || targetDir.length === 0) return;
                    const hasContent = await callApi('run_func', 'evaluate_path', targetDir);
                    async function doCreate() {
                        await callApi('move_folders', folder.path, targetDir);
                        await callApi('run_func', 'remove_symlink', folder.path);
                        await callApi('run_func', 'create_symlink', targetDir, folder.path);
                        refreshSymlink();
                    }
                    if (hasContent) {
                        showConfirm('警告', `目标文件夹中含有文件。可能出现非预期行为。\n这有可能导致以下错误: 游戏无法正常启动，点击删除软链接时同时移动目标文件夹下的所有文件。\n正常的做法是创建一个空文件夹用来盛放文件。\n如果你确定知道自己在做什么，请点击确定`, doCreate, () => {});
                    } else {
                        doCreate();
                    }
                },
                () => {}
            );
        } else if (folder.status === 'not_exist') {
            showConfirm('创建软链接',
                '现在对应位置没有目录，如果您先前手动迁移了数据，那么点击是以创建软链接',
                () => {
                    showMessage('提示', '请选择您先前迁移的文件夹',
                        async () => {
                            const targetDir = await callApi('browse_folder', 'symlink-target-dir');
                            if (!targetDir || targetDir.length === 0) return;
                            await callApi('run_func', 'create_symlink', targetDir, folder.path);
                            refreshSymlink();
                        }
                    );
                },
                () => {}
            );
        } else {
            showMessage('警告', '请先确保文件正确已安装');
        }
    } catch (error) {
        showMessage('错误', `创建软链接时发生错误\n${error}`);
    }
}

async function removeSymlink() {
    const folderName = symlinkManagerCompat.getSelectedItem();
    const folder = symlinkStatusCompat[folderName];
    try {
        if (folder.status === 'symlink') {
            showConfirm('是否要删除软链接？',
                `您已经创建了一个可用的软链接，它的目录是 ${folder.target}，是否删除？\n如果您确认继续，这将使文件夹重新回到c盘`,
                async function() {
                    await callApi('run_func', 'remove_symlink', folder.path);
                    await callApi('run_func', 'evaluate_path', folder.path);
                    await callApi('move_folders', folder.target, folder.path);
                    refreshSymlink();
                },
                () => {}
            );
        } else {
            showMessage('警告', '当前数据项不是软链接');
        }
    } catch (error) {
        showMessage('错误', `删除软链接时发生错误\n${error}`);
    }
}

window.browseInstallPackageDirectory = browseInstallPackageDirectory;
window.clearPackageDirectory = clearPackageDirectory;
window.browseInstallModDirectory = browseInstallModDirectory;
window.clearModDirectory = clearModDirectory;
window.refreshInstallPackageList = refreshInstallPackageList;
window.installSelectedPackage = installSelectedPackage;
window.deleteSelectedPackage = deleteSelectedPackage;
window.refreshInstalledPackageList = refreshInstalledPackageList;
window.useSelectedPackage = useSelectedPackage;
window.deleteInstalledPackage = deleteInstalledPackage;
window.refreshInstalledModList = refreshInstalledModList;
window.toggleMod = toggleMod;
window.openModPath = openModPath;
window.deleteSelectedMod = deleteSelectedMod;
window.loadSymlinkStatus = loadSymlinkStatus;
window.refreshSymlink = refreshSymlink;
window.openPath = openPath;
window.createSymlink = createSymlink;
window.removeSymlink = removeSymlink;
