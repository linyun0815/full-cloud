package cn.full.cloud.module.bpm.framework.rpc.config;

import cn.full.cloud.module.bpm.api.event.CrmContractStatusListener;
import cn.full.cloud.module.bpm.api.event.CrmReceivableStatusListener;
import cn.full.cloud.module.bpm.api.event.OaLeaveApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaMeetingRoomBookingStatusListener;
import cn.full.cloud.module.bpm.api.event.OaOfficialDocReceiveStatusListener;
import cn.full.cloud.module.bpm.api.event.OaOfficialDocSendStatusListener;
import cn.full.cloud.module.bpm.api.event.OaOvertimeApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaRegularApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaReimbursementStatusListener;
import cn.full.cloud.module.bpm.api.event.OaResignApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaSealApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaSupplyApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaTravelApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaTravelReimbursementStatusListener;
import cn.full.cloud.module.bpm.api.event.OaVehicleApplyStatusListener;
import cn.full.cloud.module.bpm.api.event.OaVehicleReturnStatusListener;
import cn.full.cloud.module.system.api.dept.DeptApi;
import cn.full.cloud.module.system.api.dept.PostApi;
import cn.full.cloud.module.system.api.dict.DictDataApi;
import cn.full.cloud.module.system.api.permission.PermissionApi;
import cn.full.cloud.module.system.api.permission.RoleApi;
import cn.full.cloud.module.system.api.sms.SmsSendApi;
import cn.full.cloud.module.system.api.user.AdminUserApi;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "bpmRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {RoleApi.class, DeptApi.class, PostApi.class, AdminUserApi.class, SmsSendApi.class, DictDataApi.class,
        PermissionApi.class})
public class RpcConfiguration {

    // ========== 特殊：解决微 yudao-cloud 微服务场景下，跨服务（进程）无法 Listener 的问题 ==========

    @Bean
    @ConditionalOnMissingBean(name = "crmReceivableStatusListener")
    public CrmReceivableStatusListener crmReceivableStatusListener() {
        return new CrmReceivableStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "crmContractStatusListener")
    public CrmContractStatusListener crmContractStatusListener() {
        return new CrmContractStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaLeaveApplyStatusListener")
    public OaLeaveApplyStatusListener oaLeaveApplyStatusListener() {
        return new OaLeaveApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaMeetingRoomBookingStatusListener")
    public OaMeetingRoomBookingStatusListener oaMeetingRoomBookingStatusListener() {
        return new OaMeetingRoomBookingStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaOfficialDocReceiveStatusListener")
    public OaOfficialDocReceiveStatusListener oaOfficialDocReceiveStatusListener() {
        return new OaOfficialDocReceiveStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaOfficialDocSendStatusListener")
    public OaOfficialDocSendStatusListener oaOfficialDocSendStatusListener() {
        return new OaOfficialDocSendStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaOvertimeApplyStatusListener")
    public OaOvertimeApplyStatusListener oaOvertimeApplyStatusListener() {
        return new OaOvertimeApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaRegularApplyStatusListener")
    public OaRegularApplyStatusListener oaRegularApplyStatusListener() {
        return new OaRegularApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaReimbursementStatusListener")
    public OaReimbursementStatusListener oaReimbursementStatusListener() {
        return new OaReimbursementStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaResignApplyStatusListener")
    public OaResignApplyStatusListener oaResignApplyStatusListener() {
        return new OaResignApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaSealApplyStatusListener")
    public OaSealApplyStatusListener oaSealApplyStatusListener() {
        return new OaSealApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaSupplyApplyStatusListener")
    public OaSupplyApplyStatusListener oaSupplyApplyStatusListener() {
        return new OaSupplyApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaTravelApplyStatusListener")
    public OaTravelApplyStatusListener oaTravelApplyStatusListener() {
        return new OaTravelApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaTravelReimbursementStatusListener")
    public OaTravelReimbursementStatusListener oaTravelReimbursementStatusListener() {
        return new OaTravelReimbursementStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaVehicleApplyStatusListener")
    public OaVehicleApplyStatusListener oaVehicleApplyStatusListener() {
        return new OaVehicleApplyStatusListener();
    }

    @Bean
    @ConditionalOnMissingBean(name = "oaVehicleReturnStatusListener")
    public OaVehicleReturnStatusListener oaVehicleReturnStatusListener() {
        return new OaVehicleReturnStatusListener();
    }

}
