package cn.full.cloud.module.mes.dal.mysql.wm.returnissue;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.mes.controller.admin.wm.returnissue.vo.line.MesWmReturnIssueLinePageReqVO;
import cn.full.cloud.module.mes.dal.dataobject.wm.returnissue.MesWmReturnIssueLineDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * MES 生产退料单行 Mapper
 */
@Mapper
public interface MesWmReturnIssueLineMapper extends BaseMapperX<MesWmReturnIssueLineDO> {

    default PageResult<MesWmReturnIssueLineDO> selectPage(MesWmReturnIssueLinePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<MesWmReturnIssueLineDO>()
                .eqIfPresent(MesWmReturnIssueLineDO::getIssueId, reqVO.getIssueId())
                .orderByDesc(MesWmReturnIssueLineDO::getId));
    }

    default List<MesWmReturnIssueLineDO> selectListByIssueId(Long issueId) {
        return selectList(MesWmReturnIssueLineDO::getIssueId, issueId);
    }

    default void deleteByIssueId(Long issueId) {
        delete(MesWmReturnIssueLineDO::getIssueId, issueId);
    }

}
