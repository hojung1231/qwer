const {defineConfig}=require('eslint/config');
const expo=require('eslint-config-expo/flat');
module.exports=defineConfig([expo,{ignores:['.verify-export/**','android/**','ios/**']},{rules:{'react-hooks/exhaustive-deps':'off'}}]);
