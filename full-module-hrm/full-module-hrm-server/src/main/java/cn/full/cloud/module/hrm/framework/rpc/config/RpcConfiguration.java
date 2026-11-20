package cn.full.cloud.module.hrm.framework.rpc.config;

import cn.full.cloud.module.bpm.api.task.BpmProcessInstanceApi;
import cn.full.cloud.module.system.api.dept.DeptApi;
import cn.full.cloud.module.system.api.logger.OperateLogApi;
import cn.full.cloud.module.system.api.notify.NotifyMessageSendApi;
import cn.full.cloud.module.system.api.user.AdminUserApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "hrmRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {AdminUserApi.class, DeptApi.class, OperateLogApi.class,
        NotifyMessageSendApi.class, BpmProcessInstanceApi.class})
public class RpcConfiguration {
}
