package cn.full.cloud.module.mes.framework.rpc.config;

import cn.full.cloud.module.system.api.dept.PostApi;
import cn.full.cloud.module.system.api.dict.DictDataApi;
import cn.full.cloud.module.system.api.permission.RoleApi;
import cn.full.cloud.module.system.api.user.AdminUserApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "mesRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {AdminUserApi.class, PostApi.class, RoleApi.class, DictDataApi.class})
public class RpcConfiguration {
}
